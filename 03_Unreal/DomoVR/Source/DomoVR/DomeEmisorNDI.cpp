#include "DomeEmisorNDI.h"

#include "Components/SceneCaptureComponentCube.h"
#include "Components/SceneComponent.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/TextureRenderTargetCube.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "HAL/IConsoleManager.h"
#include "ImageUtils.h"
#include "Kismet/KismetRenderingLibrary.h"
#include "Misc/FileHelper.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "MediaCapture.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "NDIMediaOutput.h"
#include "Slate/SlateBrushAsset.h"
#include "Styling/SlateBrush.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"

DEFINE_LOG_CATEGORY_STATIC(LogDomoEmisor, Log, All);

ADomeEmisorNDI::ADomeEmisorNDI()
{
	PrimaryActorTick.bCanEverTick = true;
	// Despues de todo lo que se mueve: la captura tiene que ver la escena ya actualizada.
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;

	USceneComponent* Raiz = CreateDefaultSubobject<USceneComponent>(TEXT("Raiz"));
	SetRootComponent(Raiz);

	Captura = CreateDefaultSubobject<USceneCaptureComponentCube>(TEXT("CapturaCubo"));
	Captura->SetupAttachment(Raiz);
	// Se captura a mano, una vez por cuadro, justo antes de convertir el cubo en domemaster.
	Captura->bCaptureEveryFrame = false;
	Captura->bCaptureOnMovement = false;
	// El cubo gira con el actor: asi el domemaster sale con el frente y el cenit de la camara.
	Captura->bCaptureRotation = true;
	Captura->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
	Captura->bAlwaysPersistRenderingState = true;
}

FVector ADomeEmisorNDI::PosicionOjo() const
{
	return GetActorLocation();
}

FVector ADomeEmisorNDI::PuntoDelRecorrido(float T) const
{
	// Una curva de Lissajous suave (un ocho torcido): sin esquinas, sin paradas y sin repetir
	// enseguida el mismo tramo. La camara nunca llega al lecho porque Z casi no se mueve.
	const float Fase = 2.f * PI * T / FMath::Max(DuracionCiclo, 1.f);
	return Centro + FVector(
		Radios.X * FMath::Sin(Fase),
		Radios.Y * FMath::Sin(2.f * Fase + 0.6f),
		Radios.Z * FMath::Sin(3.f * Fase + 1.1f));
}

void ADomeEmisorNDI::PrepararRenderTargets()
{
	RTCubo = NewObject<UTextureRenderTargetCube>(this);
	RTCubo->Init(LadoCubo, PF_FloatRGBA);
	RTCubo->UpdateResourceImmediate(true);

	RTDomemaster = NewObject<UTextureRenderTarget2D>(this);
	RTDomemaster->RenderTargetFormat = RTF_RGBA8;
	RTDomemaster->ClearColor = FLinearColor::Black;
	RTDomemaster->bAutoGenerateMips = false;
	RTDomemaster->InitAutoFormat(LadoDomemaster, LadoDomemaster);
	RTDomemaster->UpdateResourceImmediate(true);

	Captura->TextureTarget = RTCubo;
	// Sin iluminacion global de Lumen ni reflejos de pantalla: la escena del abismo es emisiva y de niebla,
	// y seis vistas de Lumen por cuadro no caben en el presupuesto.
	FPostProcessSettings& PP = Captura->PostProcessSettings;
	PP.bOverride_DynamicGlobalIlluminationMethod = true;
	PP.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::None;
	PP.bOverride_ReflectionMethod = true;
	PP.ReflectionMethod = EReflectionMethod::None;
	// Exposicion fija: el modo Manual usa la camara fisica (ISO, diafragma) y deja a oscuras una escena tenue;
	// con el minimo y el maximo iguales el histograma no se mueve y el brillo no respira entre un cuadro y otro.
	PP.bOverride_AutoExposureMethod = true;
	PP.AutoExposureMethod = EAutoExposureMethod::AEM_Histogram;
	PP.bOverride_AutoExposureMinBrightness = true;
	PP.AutoExposureMinBrightness = Exposicion;
	PP.bOverride_AutoExposureMaxBrightness = true;
	PP.AutoExposureMaxBrightness = Exposicion;
	PP.bOverride_AutoExposureBias = true;
	PP.AutoExposureBias = 0.f;
	Captura->PostProcessBlendWeight = 1.f;

	if (!MaterialDomemaster)
	{
		MaterialDomemaster = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Abismo/M_CuboADomemaster.M_CuboADomemaster"));
	}
	if (!MaterialDomemaster)
	{
		UE_LOG(LogDomoEmisor, Error, TEXT("No existe /Game/Abismo/M_CuboADomemaster: correr 03_Unreal/crear_abismo.ps1."));
		return;
	}
	MatDomemaster = UMaterialInstanceDynamic::Create(MaterialDomemaster, this);
	MatDomemaster->SetTextureParameterValue(TEXT("Cubo"), RTCubo);
	MatDomemaster->SetScalarParameterValue(TEXT("FovGrados"), FovDomo);
}

void ADomeEmisorNDI::IniciarNDI()
{
	if (!bEnviarNDI)
	{
		UE_LOG(LogDomoEmisor, Display, TEXT("NDI apagado: solo se dibuja el domemaster."));
		return;
	}
	SalidaNDI = NewObject<UNDIMediaOutput>(this);
	SalidaNDI->SourceName = NombreNDI;
	SalidaNDI->bOverrideDesiredSize = true;
	SalidaNDI->DesiredSize = FIntPoint(LadoDomemaster, LadoDomemaster);
	SalidaNDI->FrameRate = FFrameRate(FpsNDI, 1);
	SalidaNDI->OutputType = EMediaIOOutputType::Fill;

	CapturaNDI = SalidaNDI->CreateMediaCapture();
	if (!CapturaNDI)
	{
		UE_LOG(LogDomoEmisor, Error, TEXT("No se pudo crear la captura NDI (falta el plugin NDIMedia o Processing.NDI.Lib.x64.dll)."));
		return;
	}
	FMediaCaptureOptions Opciones;
	// Si el envio se atrasa, se salta el cuadro: no se traba el juego esperando a la red.
	Opciones.OverrunAction = EMediaCaptureOverrunAction::Skip;
	if (!CapturaNDI->CaptureTextureRenderTarget2D(RTDomemaster, Opciones))
	{
		UE_LOG(LogDomoEmisor, Error, TEXT("CaptureTextureRenderTarget2D fallo: no se anuncia la fuente NDI '%s'."), *NombreNDI);
		CapturaNDI = nullptr;
		return;
	}
	UE_LOG(LogDomoEmisor, Display, TEXT("NDI: fuente '%s', %dx%d a %d fps."), *NombreNDI, LadoDomemaster, LadoDomemaster, FpsNDI);
}

void ADomeEmisorNDI::BeginPlay()
{
	Super::BeginPlay();

	// Ajustes por linea de comandos, para probar sin abrir el editor:
	//   -AbismoNDI=Nombre  -AbismoLado=2048  -AbismoCubo=1536  -AbismoSinNDI
	FString Texto;
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoNDI="), Texto) && !Texto.IsEmpty()) { NombreNDI = Texto; }
	int32 Numero = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoLado="), Numero) && Numero >= 512) { LadoDomemaster = Numero; }
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoCubo="), Numero) && Numero >= 256) { LadoCubo = Numero; }
	if (FParse::Param(FCommandLine::Get(), TEXT("AbismoSinNDI"))) { bEnviarNDI = false; }
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoModo="), Numero)) { ModoDepuracion = Numero; }
	float Exp = 0.f;
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoExposicion="), Exp) && Exp > 0.f) { Exposicion = Exp; }

	FString Fotos;
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoFoto="), Fotos))
	{
		Fotos.ParseIntoArray(FotosAuto, TEXT(";"));
		float Cada = 0.f;
		if (FParse::Value(FCommandLine::Get(), TEXT("AbismoFotoCada="), Cada) && Cada > 0.f) { FotoCada = Cada; }
		ProximaFoto = FotoCada;
		bSalirAlFinal = FParse::Param(FCommandLine::Get(), TEXT("AbismoSalir"));
	}
	float Salto = 0.f;
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoSegundo="), Salto)) { Reloj = Salto; }

	// Sin tope, sin vsync y sin pantalla el juego corre a lo que dé la GPU y las listas de comandos de D3D12 se
	// acumulan hasta que el motor se cae ("Too many residency sets are open concurrently", medido tras ~50 s).
	// NDI anuncia FpsNDI de todos modos: el tope a esa cadencia no pierde nada.
	if (!FParse::Param(FCommandLine::Get(), TEXT("AbismoSinTope")))
	{
		if (IConsoleVariable* Tope = IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS"))) { Tope->Set(static_cast<float>(FpsNDI)); }
	}

	PrepararRenderTargets();
	IniciarNDI();
	MostrarVistaPrevia(bVistaPrevia);
	AvanceSuave = (PuntoDelRecorrido(0.5f) - PuntoDelRecorrido(0.f)).GetSafeNormal();
	if (AvanceSuave.IsNearlyZero()) { AvanceSuave = FVector::ForwardVector; }
	Avance = AvanceSuave;
}

void ADomeEmisorNDI::EndPlay(const EEndPlayReason::Type Motivo)
{
	if (CapturaNDI)
	{
		CapturaNDI->StopCapture(false);
		CapturaNDI = nullptr;
	}
	MostrarVistaPrevia(false);
	Super::EndPlay(Motivo);
}

void ADomeEmisorNDI::ColocarCamara(float Delta)
{
	Reloj += Delta * Velocidad;
	const FVector Posicion = bRecorrido ? PuntoDelRecorrido(Reloj) : GetActorLocation();
	if (bRecorrido)
	{
		const FVector Delante = (PuntoDelRecorrido(Reloj + 0.75f) - Posicion).GetSafeNormal();
		if (!Delante.IsNearlyZero())
		{
			Avance = Delante;
			// El frente sigue al avance con retraso, como una cabeza que gira despacio.
			AvanceSuave = FMath::VInterpTo(AvanceSuave, Avance, Delta, 0.9f).GetSafeNormal();
		}
	}
	FQuat Q = FRotationMatrix::MakeFromXZ(AvanceSuave, FVector::UpVector).ToQuat();
	// Balanceo: una oscilacion lenta de rodadura y de cabeceo.
	const float Rodadura = Balanceo * FMath::Sin(Reloj * 0.31f);
	const float Cabeceo = 0.5f * Balanceo * FMath::Sin(Reloj * 0.23f + 1.3f);
	Q = Q * FRotator(Cabeceo, 0.f, Rodadura).Quaternion();
	// El cenit de la cupula se inclina hacia adelante (una rotacion negativa de cabeceo lleva Z hacia X).
	Q = Q * FRotator(-InclinacionDomo, 0.f, 0.f).Quaternion();
	SetActorLocationAndRotation(Posicion, Q);
}

void ADomeEmisorNDI::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	if (!Captura || !RTCubo || !RTDomemaster) { return; }

	// F4 muestra u oculta la vista previa del domemaster (sondeo, como el resto de las teclas del proyecto).
	if (APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr)
	{
		const bool bF4 = PC->IsInputKeyDown(EKeys::F4);
		if (bF4 && !bF4Antes) { PonerVistaPrevia(!VistaPreviaWidget.IsValid()); }
		bF4Antes = bF4;
	}

	RelojReal += DeltaTime;
	// Cuadros por segundo reales, para saber cuanto cuesta el cubo (se escribe cada 5 s).
	AcumFps += DeltaTime; ++CuadrosFps;
	if (AcumFps >= 5.f)
	{
		UE_LOG(LogDomoEmisor, Display, TEXT("Abismo: %.1f fps (cubo %d, domemaster %d)"), CuadrosFps / AcumFps, LadoCubo, LadoDomemaster);
		AcumFps = 0.f; CuadrosFps = 0;
	}
	if (ProximaFoto > 0.f && RelojReal >= ProximaFoto && FotosAuto.IsValidIndex(FotosHechas))
	{
		GuardarFoto(FotosAuto[FotosHechas++]);
		ProximaFoto = RelojReal + FotoCada;
		if (FotosHechas >= FotosAuto.Num())
		{
			ProximaFoto = -1.f;
			if (bSalirAlFinal) { FPlatformMisc::RequestExit(false); }
		}
	}

	ColocarCamara(DeltaTime);
	Captura->CaptureScene();
	// Los primeros cuadros solo capturan el cubo: el material no lo lee hasta que la GPU ya lo escribio una vez.
	if (MatDomemaster && ++CuadrosCaptura > 5)
	{
		MatDomemaster->SetScalarParameterValue(TEXT("FovGrados"), FovDomo);
		MatDomemaster->SetScalarParameterValue(TEXT("Modo"), ModoDepuracion);
		UKismetRenderingLibrary::DrawMaterialToRenderTarget(this, RTDomemaster, MatDomemaster);
	}
}

void ADomeEmisorNDI::PonerVistaPrevia(bool bMostrar)
{
	bVistaPrevia = bMostrar;
	MostrarVistaPrevia(bMostrar);
}

void ADomeEmisorNDI::MostrarVistaPrevia(bool bMostrar)
{
	UGameViewportClient* Vista = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!Vista) { return; }
	if (bMostrar && !VistaPreviaWidget.IsValid() && RTDomemaster)
	{
		VistaPreviaPincel = MakeShared<FSlateBrush>();
		VistaPreviaPincel->SetResourceObject(RTDomemaster);
		VistaPreviaPincel->ImageSize = FVector2D(LadoDomemaster, LadoDomemaster);
		VistaPreviaPincel->DrawAs = ESlateBrushDrawType::Image;
		VistaPreviaWidget = SNew(SBox)
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			[
				SNew(SScaleBox)
				.Stretch(EStretch::ScaleToFit)
				[
					SNew(SImage).Image(VistaPreviaPincel.Get())
				]
			];
		Vista->AddViewportWidgetContent(VistaPreviaWidget.ToSharedRef(), 5);
	}
	else if (!bMostrar && VistaPreviaWidget.IsValid())
	{
		Vista->RemoveViewportWidgetContent(VistaPreviaWidget.ToSharedRef());
		VistaPreviaWidget.Reset();
		VistaPreviaPincel.Reset();
	}
}

bool ADomeEmisorNDI::GuardarFoto(const FString& Ruta)
{
	if (!RTDomemaster) { return false; }
	FTextureRenderTargetResource* Recurso = RTDomemaster->GameThread_GetRenderTargetResource();
	if (!Recurso) { return false; }
	TArray<FColor> Pixeles;
	Recurso->ReadPixels(Pixeles);
	if (Pixeles.Num() != RTDomemaster->SizeX * RTDomemaster->SizeY) { return false; }
	for (FColor& C : Pixeles) { C.A = 255; }
	FImage Imagen;
	Imagen.Init(RTDomemaster->SizeX, RTDomemaster->SizeY, ERawImageFormat::BGRA8);
	FMemory::Memcpy(Imagen.RawData.GetData(), Pixeles.GetData(), Pixeles.Num() * sizeof(FColor));
	TArray64<uint8> Png;
	if (!FImageUtils::CompressImage(Png, TEXT("png"), Imagen)) { return false; }
	const bool bOk = FFileHelper::SaveArrayToFile(Png, *Ruta);
	UE_LOG(LogDomoEmisor, Display, TEXT("Foto del domemaster: %s (%s)"), *Ruta, bOk ? TEXT("ok") : TEXT("fallo"));
	return bOk;
}

// Comandos de consola para probar sin abrir el editor (tambien valen en el guion de -DomoGuion).
static ADomeEmisorNDI* PrimerEmisor(UWorld* Mundo)
{
	if (!Mundo) { return nullptr; }
	for (TActorIterator<ADomeEmisorNDI> It(Mundo); It; ++It) { return *It; }
	return nullptr;
}

static FAutoConsoleCommandWithWorldAndArgs CmdAbismoFoto(TEXT("abismo.Foto"),
	TEXT("abismo.Foto Ruta.png: guarda el domemaster actual."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* Mundo)
	{
		if (ADomeEmisorNDI* E = PrimerEmisor(Mundo)) { if (Args.Num() > 0) { E->GuardarFoto(Args[0]); } }
	}));

static FAutoConsoleCommandWithWorldAndArgs CmdAbismoSegundo(TEXT("abismo.Segundo"),
	TEXT("abismo.Segundo S: salta el recorrido al segundo S."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* Mundo)
	{
		if (ADomeEmisorNDI* E = PrimerEmisor(Mundo)) { if (Args.Num() > 0) { E->IrAlSegundo(FCString::Atof(*Args[0])); } }
	}));

static FAutoConsoleCommandWithWorldAndArgs CmdAbismoVelocidad(TEXT("abismo.Velocidad"),
	TEXT("abismo.Velocidad V: velocidad del recorrido (1 normal, 0 detenido)."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* Mundo)
	{
		if (ADomeEmisorNDI* E = PrimerEmisor(Mundo)) { if (Args.Num() > 0) { E->Velocidad = FCString::Atof(*Args[0]); } }
	}));

static FAutoConsoleCommandWithWorldAndArgs CmdAbismoInclinacion(TEXT("abismo.Inclinacion"),
	TEXT("abismo.Inclinacion G: cuanto se inclina el cenit de la cupula hacia adelante (grados)."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* Mundo)
	{
		if (ADomeEmisorNDI* E = PrimerEmisor(Mundo)) { if (Args.Num() > 0) { E->InclinacionDomo = FCString::Atof(*Args[0]); } }
	}));
