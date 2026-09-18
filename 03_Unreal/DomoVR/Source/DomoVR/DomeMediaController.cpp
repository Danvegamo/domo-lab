#include "DomeMediaController.h"

#include "SpoutDomeReceiver.h"

#include "Components/InputComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FileMediaSource.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "MediaPlayer.h"
#include "MediaSoundComponent.h"
#include "MediaTexture.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogDomoMedia, Log, All);

// Nombres de los parametros de M_DomoMedia (los crea crear_media_domo.py; si
// se cambia uno aqui hay que cambiarlo alla).
namespace DomoParam
{
	static const FName Textura(TEXT("MediaTexture"));
	static const FName Formato(TEXT("Formato"));
	static const FName Brillo(TEXT("Brillo"));
	static const FName FovSala(TEXT("FovSala"));
	static const FName FovContenido(TEXT("FovContenido"));
	static const FName Yaw(TEXT("Yaw"));
	static const FName Pitch(TEXT("Pitch"));
	static const FName Roll(TEXT("Roll"));
	static const FName Horizonte(TEXT("Horizonte"));
	static const FName Curva(TEXT("Curva"));
	static const FName CentroX(TEXT("CentroX"));
	static const FName CentroY(TEXT("CentroY"));
	static const FName Escala(TEXT("Escala"));
	static const FName Rotar(TEXT("Rotar"));
	static const FName PantallaAzimut(TEXT("PantallaAzimut"));
	static const FName PantallaElevacion(TEXT("PantallaElevacion"));
	static const FName PantallaAncho(TEXT("PantallaAncho"));
	static const FName PantallaAlto(TEXT("PantallaAlto"));
	static const FName PantallaCurva(TEXT("PantallaCurva"));
	static const FName PantallaBorde(TEXT("PantallaBorde"));
	static const FName Volumen(TEXT("Volumen"));
}

namespace
{
	/** Campo flotante del cue que corresponde a un parametro, o nullptr. */
	float* CampoDelCue(FDomeCue& C, FName N)
	{
		if (N == DomoParam::Yaw) return &C.Yaw;
		if (N == DomoParam::Pitch) return &C.Pitch;
		if (N == DomoParam::Roll) return &C.Roll;
		if (N == DomoParam::Horizonte) return &C.Horizonte;
		if (N == DomoParam::Curva) return &C.Curva;
		if (N == DomoParam::FovContenido) return &C.FovContenido;
		if (N == DomoParam::CentroX) return &C.Mapping.CentroX;
		if (N == DomoParam::CentroY) return &C.Mapping.CentroY;
		if (N == DomoParam::Escala) return &C.Mapping.Escala;
		if (N == DomoParam::Rotar) return &C.Mapping.Rotar;
		if (N == DomoParam::PantallaAzimut) return &C.Pantalla.Azimut;
		if (N == DomoParam::PantallaElevacion) return &C.Pantalla.Elevacion;
		if (N == DomoParam::PantallaAncho) return &C.Pantalla.Ancho;
		if (N == DomoParam::PantallaAlto) return &C.Pantalla.Alto;
		if (N == DomoParam::PantallaBorde) return &C.Pantalla.Borde;
		if (N == DomoParam::Volumen) return &C.Volumen;
		return nullptr;
	}

	bool LeerNumero(const TSharedPtr<FJsonObject>& O, const TCHAR* Clave, float& Out)
	{
		double V = 0.0;
		if (O.IsValid() && O->TryGetNumberField(Clave, V))
		{
			Out = static_cast<float>(V);
			return true;
		}
		return false;
	}

	EDomeFormato FormatoDeTexto(FString T, bool& bOk)
	{
		bOk = true;
		T = T.ToLower().Replace(TEXT(" "), TEXT(""));
		if (T == TEXT("360") || T == TEXT("equirect") || T == TEXT("equirectangular")) return EDomeFormato::Equirect360;
		if (T == TEXT("domemaster") || T == TEXT("fisheye") || T == TEXT("180")) return EDomeFormato::Domemaster;
		if (T == TEXT("vr180")) return EDomeFormato::VR180;
		if (T == TEXT("vr180sbs") || T == TEXT("sbs")) return EDomeFormato::VR180SBS;
		if (T == TEXT("169") || T == TEXT("16:9") || T == TEXT("plano") || T == TEXT("pantalla")) return EDomeFormato::Plano169;
		bOk = false;
		return EDomeFormato::Equirect360;
	}
}

// -----------------------------------------------------------------------------

ADomeMediaController::ADomeMediaController()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	// Despues del receptor de Spout (TG_PrePhysics): si los dos tocaran la
	// malla en el mismo frame, gana la fuente elegida.
	PrimaryActorTick.TickGroup = TG_PostPhysics;

	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Raiz"));

	// Audio del video. No espacial: la sala entera escucha lo mismo, como con
	// el sistema de sonido de un domo. Arranca apagado; BeginPlay lo enciende
	// solo en mundos de juego (el editor queda en silencio).
	MediaSound = CreateDefaultSubobject<UMediaSoundComponent>(TEXT("SonidoVideo"));
	MediaSound->SetupAttachment(RootComponent);
	MediaSound->bAutoActivate = false;
	MediaSound->bAllowSpatialization = false;
	MediaSound->bIsUISound = true;
	MediaSound->Channels = EMediaSoundChannels::Stereo;
}

bool ADomeMediaController::ShouldTickIfViewportsOnly() const
{
	// Igual que ASpoutDomeReceiver: tickea en el viewport del editor sin Play.
	return true;
}

bool ADomeMediaController::EsMundoDeJuego() const
{
	const UWorld* W = GetWorld();
	return W && W->IsGameWorld();
}

bool ADomeMediaController::EstaActivo() const
{
	const UWorld* W = GetWorld();
	if (!W)
	{
		return false;
	}
	if (W->IsGameWorld())
	{
		return true;
	}
	if (W->WorldType != EWorldType::Editor || !bReproducirEnEditor)
	{
		return false;
	}
	// Durante una sesion de PIE manda la copia del mundo de juego: la del
	// editor se queda quieta para no pelearse por MP_Domo (es un asset
	// compartido).
	if (GEngine)
	{
		for (const FWorldContext& Ctx : GEngine->GetWorldContexts())
		{
			if (Ctx.WorldType == EWorldType::PIE && Ctx.World())
			{
				return false;
			}
		}
	}
	return true;
}

void ADomeMediaController::BeginPlay()
{
	Super::BeginPlay();

	if (!EsMundoDeJuego())
	{
		return;
	}

	if (MediaSound && MediaPlayer)
	{
		MediaSound->SetMediaPlayer(MediaPlayer);
		MediaSound->SetEnableEnvelopeFollowing(true);
		MediaSound->Start();
	}

	// La fuente: en el editor (Play) la del actor, Spout; fuera del editor
	// (build, -game) FuenteFueraDelEditor, Media; -DomoFuente= pisa las dos.
	FString FuenteCmd;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoFuente="), FuenteCmd))
	{
		Fuente = FuenteCmd.Equals(TEXT("Spout"), ESearchCase::IgnoreCase) ? EDomeFuente::Spout : EDomeFuente::Media;
	}
	else if (!GIsEditor)
	{
		Fuente = FuenteFueraDelEditor;
	}
	UE_LOG(LogDomoMedia, Display, TEXT("Fuente al arrancar: %s"), Fuente == EDomeFuente::Media ? TEXT("Media") : TEXT("Spout"));

	FString Preset;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoPreset="), Preset))
	{
		AplicarPreset(Preset);
	}

	Inicializar();
	ConfigurarTeclado();

	FString RutaGuion;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoGuion="), RutaGuion))
	{
		RutaGuion = FPaths::ConvertRelativePathToFull(RutaGuion);
		if (FFileHelper::LoadFileToStringArray(Guion, *RutaGuion))
		{
			UE_LOG(LogDomoMedia, Display, TEXT("Guion de prueba: %s (%d lineas)"), *RutaGuion, Guion.Num());
		}
		else
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("No se pudo leer el guion %s"), *RutaGuion);
		}
	}
}

bool ADomeMediaController::AplicarPreset(const FString& Nombre)
{
	// Los valores de "VR" son los de fabrica del proyecto (DefaultEngine.ini);
	// "Render" sube la resolucion interna (TSR la reconstruye a la salida), usa
	// hit lighting en Lumen (reflejos de la cupula en el metal y el barniz con
	// el material real, no con la cache de superficie) y afina el muestreo.
	// Ver 04_Docs/02_Sala_Unreal.md, seccion "Presets VR y Render".
	struct FValor { const TCHAR* CVar; const TCHAR* VR; const TCHAR* Render; };
	static const FValor Tabla[] = {
		{ TEXT("r.ScreenPercentage"), TEXT("100"), TEXT("200") },
		{ TEXT("r.TSR.History.ScreenPercentage"), TEXT("100"), TEXT("200") },
		{ TEXT("r.Lumen.HardwareRayTracing.LightingMode"), TEXT("0"), TEXT("2") },
		{ TEXT("r.Lumen.Reflections.DownsampleFactor"), TEXT("2"), TEXT("1") },
		{ TEXT("r.Lumen.Reflections.MaxRoughnessToTrace"), TEXT("0.4"), TEXT("0.6") },
		{ TEXT("r.Lumen.ScreenProbeGather.DownsampleFactor"), TEXT("16"), TEXT("8") },
		{ TEXT("r.Lumen.ScreenProbeGather.TracingOctahedronResolution"), TEXT("8"), TEXT("12") },
		{ TEXT("r.SkyLight.RealTimeReflectionCapture.TimeSlice"), TEXT("0"), TEXT("0") },
	};
	const bool bRender = Nombre.Equals(TEXT("Render"), ESearchCase::IgnoreCase);
	if (!bRender && !Nombre.Equals(TEXT("VR"), ESearchCase::IgnoreCase))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("Preset desconocido '%s' (VR o Render)."), *Nombre);
		return false;
	}
	for (const FValor& V : Tabla)
	{
		if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(V.CVar))
		{
			Var->Set(bRender ? V.Render : V.VR, ECVF_SetByConsole);
		}
		else
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("Preset %s: no existe %s en esta version del motor."), *Nombre, V.CVar);
		}
	}
	UE_LOG(LogDomoMedia, Display, TEXT("Preset de calidad: %s"), bRender ? TEXT("Render") : TEXT("VR"));
	return true;
}

void ADomeMediaController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (MediaPlayer)
	{
		MediaPlayer->OnEndReached.RemoveDynamic(this, &ADomeMediaController::AlTerminarVideo);
		MediaPlayer->OnMediaOpenFailed.RemoveDynamic(this, &ADomeMediaController::AlFallarApertura);
		if (EsMundoDeJuego())
		{
			MediaPlayer->Close();
		}
	}
	if (MediaSound && EsMundoDeJuego())
	{
		MediaSound->Stop();
	}
	Super::EndPlay(EndPlayReason);
}

void ADomeMediaController::Inicializar()
{
	if (bInicializado)
	{
		return;
	}
	bInicializado = true;

	if (!MediaPlayer || !MediaTexture || !MediaMaterial || !TargetMeshComponent)
	{
		UE_LOG(LogDomoMedia, Warning,
			TEXT("%s: faltan referencias (MediaPlayer, MediaTexture, MediaMaterial o TargetMeshComponent). ")
			TEXT("Correr 03_Unreal/crear_media_domo.ps1."), *GetName());
		return;
	}

	if (MediaTexture->GetMediaPlayer() != MediaPlayer)
	{
		MediaTexture->SetMediaPlayer(MediaPlayer);
	}

	DynamicMaterial = UMaterialInstanceDynamic::Create(MediaMaterial, this);
	// Transitoria: si el editor guarda el nivel con la cupula mostrando video,
	// la referencia se guarda nula y la malla vuelve a su material de siempre.
	DynamicMaterial->SetFlags(RF_Transient);

	MediaPlayer->OnEndReached.AddUniqueDynamic(this, &ADomeMediaController::AlTerminarVideo);
	MediaPlayer->OnMediaOpenFailed.AddUniqueDynamic(this, &ADomeMediaController::AlFallarApertura);

	CargarPlaylist(ResolverRutaPlaylist());
	if (Cues.Num() > 0)
	{
		AplicarParametros(Cues[FMath::Clamp(CueActual, 0, Cues.Num() - 1)]);
	}
	AplicarFuente();
}

FString ADomeMediaController::ResolverRutaPlaylist() const
{
	FString Ruta;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoPlaylist="), Ruta))
	{
		return FPaths::ConvertRelativePathToFull(Ruta);
	}
#if WITH_EDITOR
	if (GIsEditor && !RutaPlaylistEditor.IsEmpty())
	{
		return RutaPlaylistEditor;
	}
#endif
	if (FPaths::IsRelative(PlaylistPath))
	{
		return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / PlaylistPath);
	}
	return PlaylistPath;
}

bool ADomeMediaController::CargarPlaylist(const FString& Ruta)
{
	Cues.Reset();
	CarpetaPlaylist = FPaths::GetPath(Ruta);

	FString Texto;
	if (!FFileHelper::LoadFileToString(Texto, *Ruta))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("No existe la playlist %s. La cupula queda en negro."), *Ruta);
		Mensaje(FString::Printf(TEXT("Sin playlist: %s"), *Ruta), 8.f);
		return false;
	}

	TSharedPtr<FJsonObject> Raiz;
	const TSharedRef<TJsonReader<>> Lector = TJsonReaderFactory<>::Create(Texto);
	if (!FJsonSerializer::Deserialize(Lector, Raiz) || !Raiz.IsValid())
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("La playlist %s no es JSON valido: %s"), *Ruta, *Lector->GetErrorMessage());
		Mensaje(TEXT("Playlist con errores de JSON (ver log)"), 8.f);
		return false;
	}

	FString Carpeta;
	if (Raiz->TryGetStringField(TEXT("carpeta"), Carpeta) && !Carpeta.IsEmpty())
	{
		CarpetaPlaylist = FPaths::IsRelative(Carpeta) ? FPaths::Combine(CarpetaPlaylist, Carpeta) : Carpeta;
	}

	const TArray<TSharedPtr<FJsonValue>>* Lista = nullptr;
	if (!Raiz->TryGetArrayField(TEXT("cues"), Lista) || !Lista)
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("La playlist %s no tiene la lista \"cues\"."), *Ruta);
		return false;
	}

	for (const TSharedPtr<FJsonValue>& Valor : *Lista)
	{
		const TSharedPtr<FJsonObject> O = Valor.IsValid() ? Valor->AsObject() : nullptr;
		if (!O.IsValid())
		{
			continue;
		}
		FDomeCue C;
		O->TryGetStringField(TEXT("archivo"), C.Archivo);
		if (C.Archivo.IsEmpty())
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("Cue %d sin \"archivo\"; se salta."), Cues.Num());
			continue;
		}
		if (!O->TryGetStringField(TEXT("nombre"), C.Nombre) || C.Nombre.IsEmpty())
		{
			C.Nombre = FPaths::GetBaseFilename(C.Archivo);
		}

		// Por tipo y no con TryGetNumberField: ese convierte el texto "360" en
		// el numero 360, que recortado a 0..4 daba el formato 4 (pasaba).
		const TSharedPtr<FJsonValue> CampoFormato = O->TryGetField(TEXT("formato"));
		if (CampoFormato.IsValid() && CampoFormato->Type == EJson::String)
		{
			bool bOk = false;
			C.Formato = FormatoDeTexto(CampoFormato->AsString(), bOk);
			if (!bOk)
			{
				UE_LOG(LogDomoMedia, Warning, TEXT("Cue '%s': formato '%s' desconocido; se usa 360."), *C.Nombre, *CampoFormato->AsString());
			}
		}
		else if (CampoFormato.IsValid() && CampoFormato->Type == EJson::Number)
		{
			C.Formato = static_cast<EDomeFormato>(FMath::Clamp(FMath::RoundToInt(CampoFormato->AsNumber()), 0, 4));
		}

		LeerNumero(O, TEXT("yaw"), C.Yaw);
		LeerNumero(O, TEXT("pitch"), C.Pitch);
		LeerNumero(O, TEXT("roll"), C.Roll);
		LeerNumero(O, TEXT("horizonte"), C.Horizonte);
		LeerNumero(O, TEXT("curva"), C.Curva);
		LeerNumero(O, TEXT("fovContenido"), C.FovContenido);
		LeerNumero(O, TEXT("volumen"), C.Volumen);
		O->TryGetBoolField(TEXT("loop"), C.Loop);

		const TSharedPtr<FJsonObject>* Map = nullptr;
		if (O->TryGetObjectField(TEXT("mapping"), Map) && Map)
		{
			LeerNumero(*Map, TEXT("centroX"), C.Mapping.CentroX);
			LeerNumero(*Map, TEXT("centroY"), C.Mapping.CentroY);
			LeerNumero(*Map, TEXT("escala"), C.Mapping.Escala);
			LeerNumero(*Map, TEXT("rotar"), C.Mapping.Rotar);
		}
		const TSharedPtr<FJsonObject>* Pan = nullptr;
		if (O->TryGetObjectField(TEXT("pantalla"), Pan) && Pan)
		{
			LeerNumero(*Pan, TEXT("azimut"), C.Pantalla.Azimut);
			LeerNumero(*Pan, TEXT("elevacion"), C.Pantalla.Elevacion);
			LeerNumero(*Pan, TEXT("ancho"), C.Pantalla.Ancho);
			LeerNumero(*Pan, TEXT("alto"), C.Pantalla.Alto);
			LeerNumero(*Pan, TEXT("borde"), C.Pantalla.Borde);
			(*Pan)->TryGetBoolField(TEXT("curva"), C.Pantalla.bCurva);
		}
		Cues.Add(C);
	}

	CueActual = Cues.Num() > 0 ? FMath::Clamp(CueActual, 0, Cues.Num() - 1) : 0;
	UE_LOG(LogDomoMedia, Display, TEXT("Playlist %s: %d cues."), *Ruta, Cues.Num());
	return Cues.Num() > 0;
}

void ADomeMediaController::AplicarParametros(const FDomeCue& C)
{
	if (!DynamicMaterial)
	{
		return;
	}
	UMaterialInstanceDynamic* M = DynamicMaterial;
	M->SetTextureParameterValue(DomoParam::Textura, MediaTexture);
	M->SetScalarParameterValue(DomoParam::Formato, static_cast<float>(static_cast<uint8>(C.Formato)));
	M->SetScalarParameterValue(DomoParam::FovSala, FovSala);
	M->SetScalarParameterValue(DomoParam::FovContenido, C.FovContenido);
	M->SetScalarParameterValue(DomoParam::Yaw, C.Yaw);
	M->SetScalarParameterValue(DomoParam::Pitch, C.Pitch);
	M->SetScalarParameterValue(DomoParam::Roll, C.Roll);
	M->SetScalarParameterValue(DomoParam::Horizonte, C.Horizonte);
	M->SetScalarParameterValue(DomoParam::Curva, C.Curva);
	M->SetScalarParameterValue(DomoParam::CentroX, C.Mapping.CentroX);
	M->SetScalarParameterValue(DomoParam::CentroY, C.Mapping.CentroY);
	M->SetScalarParameterValue(DomoParam::Escala, C.Mapping.Escala);
	M->SetScalarParameterValue(DomoParam::Rotar, C.Mapping.Rotar);
	M->SetScalarParameterValue(DomoParam::PantallaAzimut, C.Pantalla.Azimut);
	M->SetScalarParameterValue(DomoParam::PantallaElevacion, C.Pantalla.Elevacion);
	M->SetScalarParameterValue(DomoParam::PantallaAncho, C.Pantalla.Ancho);
	M->SetScalarParameterValue(DomoParam::PantallaAlto, C.Pantalla.Alto);
	M->SetScalarParameterValue(DomoParam::PantallaCurva, C.Pantalla.bCurva ? 1.f : 0.f);
	M->SetScalarParameterValue(DomoParam::PantallaBorde, C.Pantalla.Borde);
}

void ADomeMediaController::AbrirCue(int32 Indice)
{
	if (!Cues.IsValidIndex(Indice))
	{
		Mensaje(TEXT("La playlist no tiene cues"));
		return;
	}
	CueActual = Indice;
	const FDomeCue& C = Cues[Indice];
	AplicarParametros(C);

	if (Fuente != EDomeFuente::Media || !MediaPlayer)
	{
		bCueAbierto = false;
		return;
	}

	FString Ruta = C.Archivo;
	if (FPaths::IsRelative(Ruta))
	{
		Ruta = FPaths::Combine(CarpetaPlaylist, Ruta);
	}
	Ruta = FPaths::ConvertRelativePathToFull(Ruta);

	if (!FPaths::FileExists(Ruta))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("Cue %d '%s': no existe el archivo %s"), Indice + 1, *C.Nombre, *Ruta);
		Mensaje(FString::Printf(TEXT("Cue %d: falta %s"), Indice + 1, *FPaths::GetCleanFilename(Ruta)), 6.f);
		MediaPlayer->Close();
		bCueAbierto = false;
		return;
	}

	if (!FuenteArchivo)
	{
		FuenteArchivo = NewObject<UFileMediaSource>(this, NAME_None, RF_Transient);
	}
	FuenteArchivo->SetFilePath(Ruta);

	MediaPlayer->SetDesiredPlayerName(Reproductor);
	MediaPlayer->PlayOnOpen = true;
	MediaPlayer->SetLooping(C.Loop);
	bPendienteAvanzar = false;
	UltimoReintento = FPlatformTime::Seconds();
	const bool bOk = MediaPlayer->OpenSource(FuenteArchivo);
	bCueAbierto = bOk;

	UE_LOG(LogDomoMedia, Display, TEXT("Cue %d/%d '%s' (%s, formato %d, loop %d): %s"),
		Indice + 1, Cues.Num(), *C.Nombre, *Ruta, static_cast<int32>(C.Formato), C.Loop ? 1 : 0,
		bOk ? TEXT("abriendo") : TEXT("OpenSource devolvio false"));
	Mensaje(FString::Printf(TEXT("Cue %d/%d  %s"), Indice + 1, Cues.Num(), *C.Nombre));
}

void ADomeMediaController::AplicarFuente()
{
	if (Fuente == EDomeFuente::Media)
	{
		if (SpoutReceiver)
		{
			SpoutReceiver->SetActorTickEnabled(false);
		}
		AsegurarMaterialEnCupula();
		if (!bCueAbierto)
		{
			AbrirCue(CueActual);
		}
		else if (MediaPlayer && !bNegro)
		{
			MediaPlayer->Play();
		}
	}
	else
	{
		if (MediaPlayer)
		{
			MediaPlayer->Close();
		}
		bCueAbierto = false;
		if (SpoutReceiver)
		{
			SpoutReceiver->SetActorTickEnabled(true);
			SpoutReceiver->ReaplicarMaterial();
		}
	}
}

void ADomeMediaController::AsegurarMaterialEnCupula()
{
	if (TargetMeshComponent && DynamicMaterial && TargetMeshComponent->GetMaterial(TargetMaterialSlot) != DynamicMaterial)
	{
		TargetMeshComponent->SetMaterial(TargetMaterialSlot, DynamicMaterial);
	}
}

void ADomeMediaController::ActualizarNegroYVolumen(float DeltaSeconds)
{
	const float Objetivo = bNegro ? 1.f : 0.f;
	const float Paso = SegundosFundido > KINDA_SMALL_NUMBER ? DeltaSeconds / SegundosFundido : 1.f;
	AlfaNegro = FMath::Clamp(AlfaNegro + FMath::Sign(Objetivo - AlfaNegro) * FMath::Min(Paso, FMath::Abs(Objetivo - AlfaNegro)), 0.f, 1.f);

	if (DynamicMaterial)
	{
		DynamicMaterial->SetScalarParameterValue(DomoParam::Brillo, Brillo * (1.f - AlfaNegro));
	}
	if (MediaSound && EsMundoDeJuego())
	{
		const float Vol = Cues.IsValidIndex(CueActual) ? Cues[CueActual].Volumen : 1.f;
		MediaSound->SetVolumeMultiplier(FMath::Max(Vol * (1.f - AlfaNegro), 0.0001f));
	}
}

void ADomeMediaController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!EstaActivo())
	{
		return;
	}
	if (!bInicializado)
	{
		Inicializar();
	}
	if (!DynamicMaterial)
	{
		return;
	}

	if (Fuente == EDomeFuente::Media)
	{
		// El receptor de Spout arranca tickeando; mientras la fuente sea Media
		// se queda apagado para que no le devuelva a la cupula su material.
		if (SpoutReceiver && SpoutReceiver->IsActorTickEnabled())
		{
			SpoutReceiver->SetActorTickEnabled(false);
		}
		AsegurarMaterialEnCupula();

		if (bPendienteAvanzar)
		{
			bPendienteAvanzar = false;
			Next();
		}

		// Tras una sesion de PIE el reproductor queda cerrado (lo cierra la
		// copia de juego al terminar): la copia del editor lo vuelve a abrir.
		const double Ahora = FPlatformTime::Seconds();
		if (bCueAbierto && MediaPlayer && MediaPlayer->IsClosed() && Ahora - UltimoReintento > 2.0)
		{
			AbrirCue(CueActual);
		}
	}

	ActualizarNegroYVolumen(DeltaSeconds);

	if (EsMundoDeJuego())
	{
		if (bControlTeclado && !InputComponent)
		{
			ConfigurarTeclado();
		}
		CorrerGuion(DeltaSeconds);
	}
}

// --- Funciones publicas -------------------------------------------------------

void ADomeMediaController::Play()
{
	if (Fuente != EDomeFuente::Media)
	{
		SetFuente(EDomeFuente::Media);
		return;
	}
	if (!bCueAbierto)
	{
		AbrirCue(CueActual);
	}
	else if (MediaPlayer)
	{
		MediaPlayer->Play();
	}
}

void ADomeMediaController::Pause()
{
	if (MediaPlayer)
	{
		MediaPlayer->Pause();
	}
}

void ADomeMediaController::TogglePause()
{
	if (MediaPlayer && MediaPlayer->IsPlaying())
	{
		Pause();
		Mensaje(TEXT("Pausa"));
	}
	else
	{
		Play();
		Mensaje(TEXT("Play"));
	}
}

void ADomeMediaController::Next()
{
	if (Cues.Num() > 0)
	{
		GoToCue((CueActual + 1) % Cues.Num());
	}
}

void ADomeMediaController::Prev()
{
	if (Cues.Num() > 0)
	{
		GoToCue((CueActual - 1 + Cues.Num()) % Cues.Num());
	}
}

void ADomeMediaController::GoToCue(int32 Indice)
{
	if (!Cues.IsValidIndex(Indice))
	{
		Mensaje(FString::Printf(TEXT("No hay cue %d (la playlist tiene %d)"), Indice + 1, Cues.Num()));
		return;
	}
	if (!bInicializado)
	{
		CueActual = Indice;
		return;
	}
	AbrirCue(Indice);
}

void ADomeMediaController::Reiniciar()
{
	if (MediaPlayer && bCueAbierto)
	{
		MediaPlayer->Rewind();
		MediaPlayer->Play();
	}
}

void ADomeMediaController::SetParam(FName Nombre, float Valor)
{
	if (Nombre == DomoParam::Brillo)
	{
		Brillo = Valor;
		return;
	}
	if (Nombre == DomoParam::FovSala)
	{
		FovSala = Valor;
	}
	if (Cues.IsValidIndex(CueActual))
	{
		FDomeCue& C = Cues[CueActual];
		if (float* Campo = CampoDelCue(C, Nombre))
		{
			*Campo = Valor;
		}
		else if (Nombre == DomoParam::Formato)
		{
			C.Formato = static_cast<EDomeFormato>(FMath::Clamp(FMath::RoundToInt(Valor), 0, 4));
		}
		else if (Nombre == DomoParam::PantallaCurva)
		{
			C.Pantalla.bCurva = Valor > 0.5f;
		}
		else if (DynamicMaterial)
		{
			// Parametro del material que no es parte del cue (EspejoU, FovSala...).
			DynamicMaterial->SetScalarParameterValue(Nombre, Valor);
			return;
		}
		AplicarParametros(C);
	}
	else if (DynamicMaterial)
	{
		DynamicMaterial->SetScalarParameterValue(Nombre, Valor);
	}
}

void ADomeMediaController::Blackout(bool bActivar)
{
	bNegro = bActivar;
	Mensaje(bNegro ? TEXT("Negro") : TEXT("Imagen"));
}

void ADomeMediaController::ToggleBlackout()
{
	Blackout(!bNegro);
}

void ADomeMediaController::SetFuente(EDomeFuente NuevaFuente)
{
	Fuente = NuevaFuente;
	if (bInicializado)
	{
		AplicarFuente();
	}
	Mensaje(Fuente == EDomeFuente::Media ? TEXT("Fuente: Media") : TEXT("Fuente: Spout"));
}

void ADomeMediaController::ToggleFuente()
{
	SetFuente(Fuente == EDomeFuente::Media ? EDomeFuente::Spout : EDomeFuente::Media);
}

bool ADomeMediaController::RecargarPlaylist()
{
	const bool bOk = CargarPlaylist(ResolverRutaPlaylist());
	if (bOk && Fuente == EDomeFuente::Media)
	{
		AbrirCue(FMath::Clamp(CueActual, 0, Cues.Num() - 1));
	}
	return bOk;
}

FString ADomeMediaController::GetNombreCue(int32 Indice) const
{
	return Cues.IsValidIndex(Indice) ? Cues[Indice].Nombre : FString();
}

FString ADomeMediaController::DescribirEstado() const
{
	FString Rep = TEXT("-");
	float Tiempo = 0.f, Duracion = 0.f, Tasa = 0.f;
	int32 Audio = 0, VideoW = 0, VideoH = 0;
	if (MediaPlayer)
	{
		Rep = MediaPlayer->GetPlayerName().ToString();
		Tiempo = static_cast<float>(MediaPlayer->GetTime().GetTotalSeconds());
		Duracion = static_cast<float>(MediaPlayer->GetDuration().GetTotalSeconds());
		Tasa = MediaPlayer->GetRate();
		Audio = MediaPlayer->GetNumTracks(EMediaPlayerTrack::Audio);
	}
	if (MediaTexture)
	{
		VideoW = MediaTexture->GetWidth();
		VideoH = MediaTexture->GetHeight();
	}
	const float Envolvente = MediaSound ? MediaSound->GetEnvelopeValue() : 0.f;
	return FString::Printf(
		TEXT("fuente=%s cue=%d/%d '%s' reproductor=%s t=%.2f/%.2f tasa=%.2f textura=%dx%d pistas_audio=%d envolvente_audio=%.4f negro=%d"),
		Fuente == EDomeFuente::Media ? TEXT("Media") : TEXT("Spout"), CueActual + 1, Cues.Num(), *GetNombreCue(CueActual),
		*Rep, Tiempo, Duracion, Tasa, VideoW, VideoH, Audio, Envolvente, bNegro ? 1 : 0);
}

// --- Eventos del reproductor --------------------------------------------------

void ADomeMediaController::AlTerminarVideo()
{
	if (!EstaActivo() || !Cues.IsValidIndex(CueActual))
	{
		return;
	}
	if (!Cues[CueActual].Loop && bAutoAvanzar)
	{
		// Se difiere al Tick: abrir otro archivo desde dentro del evento del
		// propio reproductor no es seguro.
		bPendienteAvanzar = true;
	}
}

void ADomeMediaController::AlFallarApertura(FString Url)
{
	if (!EstaActivo())
	{
		return;
	}
	UE_LOG(LogDomoMedia, Warning, TEXT("No se pudo abrir %s con %s. Revisar el codec (H.264 o HEVC en .mp4; ver 04_Docs/06_Unreal_standalone.md)."),
		*Url, *Reproductor.ToString());
	Mensaje(FString::Printf(TEXT("No se pudo abrir %s"), *FPaths::GetCleanFilename(Url)), 6.f);
	// No reintentar en bucle: queda cerrado hasta el proximo cambio de cue.
	bCueAbierto = false;
}

// --- Teclado, mensajes y guion ------------------------------------------------

void ADomeMediaController::ConfigurarTeclado()
{
	if (!bControlTeclado || !GetWorld())
	{
		return;
	}
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (!PC)
	{
		return;
	}
	EnableInput(PC);
	if (!InputComponent)
	{
		return;
	}
	InputComponent->KeyBindings.Reset();
	InputComponent->BindKey(EKeys::Right, IE_Pressed, this, &ADomeMediaController::TeclaSiguiente);
	InputComponent->BindKey(EKeys::PageDown, IE_Pressed, this, &ADomeMediaController::TeclaSiguiente);
	InputComponent->BindKey(EKeys::Left, IE_Pressed, this, &ADomeMediaController::TeclaAnterior);
	InputComponent->BindKey(EKeys::PageUp, IE_Pressed, this, &ADomeMediaController::TeclaAnterior);
	InputComponent->BindKey(EKeys::B, IE_Pressed, this, &ADomeMediaController::TeclaNegro);
	InputComponent->BindKey(EKeys::Period, IE_Pressed, this, &ADomeMediaController::TeclaNegro);
	InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &ADomeMediaController::TeclaPausa);
	InputComponent->BindKey(EKeys::Home, IE_Pressed, this, &ADomeMediaController::TeclaReiniciar);
	InputComponent->BindKey(EKeys::S, IE_Pressed, this, &ADomeMediaController::TeclaFuente);
	InputComponent->BindKey(EKeys::F1, IE_Pressed, this, &ADomeMediaController::TeclaAyuda);

	const FKey Numeros[] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five,
		EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine };
	for (int32 i = 0; i < UE_ARRAY_COUNT(Numeros); ++i)
	{
		FInputKeyBinding Enlace(FInputChord(Numeros[i]), IE_Pressed);
		Enlace.KeyDelegate.GetDelegateForManualSet().BindWeakLambda(this, [this, i]() { TeclaCue(i); });
		InputComponent->KeyBindings.Add(Enlace);
	}
}

void ADomeMediaController::TeclaAyuda()
{
	Mensaje(TEXT("Flechas / RePag AvPag: cue   1-9: ir al cue   B o punto: negro   Espacio: pausa   Inicio: reiniciar   S: Spout/Media"), 8.f);
	Mensaje(DescribirEstado(), 8.f);
}

void ADomeMediaController::Mensaje(const FString& Texto, float Segundos) const
{
	UE_LOG(LogDomoMedia, Display, TEXT("%s"), *Texto);
	if (GEngine && EsMundoDeJuego())
	{
		GEngine->AddOnScreenDebugMessage(-1, Segundos, FColor(120, 220, 255), Texto);
	}
}

void ADomeMediaController::CorrerGuion(float DeltaSeconds)
{
	if (LineaGuion >= Guion.Num())
	{
		return;
	}
	if (EsperaGuion > 0.f)
	{
		EsperaGuion -= DeltaSeconds;
		return;
	}
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	while (LineaGuion < Guion.Num() && EsperaGuion <= 0.f)
	{
		const FString Linea = Guion[LineaGuion++].TrimStartAndEnd();
		if (Linea.IsEmpty() || Linea.StartsWith(TEXT("#")))
		{
			continue;
		}
		UE_LOG(LogDomoMedia, Display, TEXT("Guion> %s"), *Linea);
		FString Resto;
		if (Linea.Split(TEXT(" "), nullptr, &Resto) && Linea.StartsWith(TEXT("esperar")))
		{
			EsperaGuion = FCString::Atof(*Resto);
			continue;
		}
		if (PC)
		{
			PC->ConsoleCommand(Linea, true);
		}
		else if (GEngine)
		{
			GEngine->Exec(GetWorld(), *Linea);
		}
	}
}

#if WITH_EDITOR
void ADomeMediaController::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	Super::PostEditChangeProperty(PropertyChangedEvent);
	const FName Prop = PropertyChangedEvent.GetPropertyName();
	if (!bInicializado)
	{
		return;
	}
	if (Prop == GET_MEMBER_NAME_CHECKED(ADomeMediaController, Fuente))
	{
		AplicarFuente();
	}
	else if (Prop == GET_MEMBER_NAME_CHECKED(ADomeMediaController, FovSala) && Cues.IsValidIndex(CueActual))
	{
		AplicarParametros(Cues[CueActual]);
	}
}
#endif

ADomeMediaController* ADomeMediaController::Buscar(UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<ADomeMediaController> It(World); It; ++It)
	{
		return *It;
	}
	return nullptr;
}

// --- Comandos de consola domo.* -----------------------------------------------
// Sirven para operar desde la consola (tecla ~), desde un guion de prueba
// (-DomoGuion=) y desde Remote Control. En el build Development la consola esta
// disponible; en Shipping no.

namespace
{
	template <typename TFunc>
	void ConControlador(UWorld* World, TFunc&& Func)
	{
		if (ADomeMediaController* C = ADomeMediaController::Buscar(World))
		{
			Func(*C);
		}
		else
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("No hay DomeMediaController en este nivel."));
		}
	}

	FAutoConsoleCommandWithWorldAndArgs CmdCue(TEXT("domo.Cue"), TEXT("domo.Cue N: ir al cue N (desde 1)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C) { C.GoToCue(A.Num() > 0 ? FCString::Atoi(*A[0]) - 1 : 0); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSiguiente(TEXT("domo.Siguiente"), TEXT("Siguiente cue."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.Next(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAnterior(TEXT("domo.Anterior"), TEXT("Cue anterior."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.Prev(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdNegro(TEXT("domo.Negro"), TEXT("domo.Negro [0|1]: fundido a negro (sin argumento, alterna)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() > 0) { C.Blackout(FCString::Atoi(*A[0]) != 0); }
				else { C.ToggleBlackout(); }
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPausa(TEXT("domo.Pausa"), TEXT("Pausa o play."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.TogglePause(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdParam(TEXT("domo.Param"), TEXT("domo.Param Nombre Valor: Yaw, Pitch, Roll, Horizonte, Curva, FovContenido, CentroX, CentroY, Escala, Rotar, Formato, Brillo, Volumen, Pantalla*."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (A.Num() < 2)
			{
				UE_LOG(LogDomoMedia, Warning, TEXT("Uso: domo.Param Nombre Valor"));
				return;
			}
			ConControlador(W, [&](ADomeMediaController& C) { C.SetParam(FName(*A[0]), FCString::Atof(*A[1])); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdFuente(TEXT("domo.Fuente"), TEXT("domo.Fuente Spout|Media (sin argumento, alterna)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() == 0) { C.ToggleFuente(); }
				else { C.SetFuente(A[0].Equals(TEXT("Spout"), ESearchCase::IgnoreCase) ? EDomeFuente::Spout : EDomeFuente::Media); }
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPreset(TEXT("domo.Preset"), TEXT("domo.Preset VR|Render: calidad liviana para el visor o de captura."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld*)
		{
			ADomeMediaController::AplicarPreset(A.Num() > 0 ? A[0] : FString(TEXT("VR")));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRecargar(TEXT("domo.Recargar"), TEXT("Vuelve a leer la playlist."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.RecargarPlaylist(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdEstado(TEXT("domo.Estado"), TEXT("Escribe en el log el estado del reproductor."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { UE_LOG(LogDomoMedia, Display, TEXT("Estado: %s"), *C.DescribirEstado()); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCamara(TEXT("domo.Camara"),
		TEXT("domo.Camara X Y Z Pitch Yaw [FOV]: mueve al jugador (cm, grados). Para capturas de verificacion."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			APlayerController* PC = W ? W->GetFirstPlayerController() : nullptr;
			if (!PC || A.Num() < 5)
			{
				UE_LOG(LogDomoMedia, Warning, TEXT("Uso: domo.Camara X Y Z Pitch Yaw [FOV] (en un mundo de juego)"));
				return;
			}
			const FVector Pos(FCString::Atof(*A[0]), FCString::Atof(*A[1]), FCString::Atof(*A[2]));
			const FRotator Rot(FCString::Atof(*A[3]), FCString::Atof(*A[4]), 0.f);
			if (APawn* P = PC->GetPawn())
			{
				P->SetActorLocation(Pos, false, nullptr, ETeleportType::TeleportPhysics);
				P->SetActorRotation(Rot);
			}
			PC->SetControlRotation(Rot);
			if (A.Num() > 5 && PC->PlayerCameraManager)
			{
				PC->PlayerCameraManager->SetFOV(FCString::Atof(*A[5]));
			}
		}));
}
