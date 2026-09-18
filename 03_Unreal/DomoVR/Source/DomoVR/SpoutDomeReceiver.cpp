#include "SpoutDomeReceiver.h"

#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/Texture2D.h"
#include "HAL/PlatformTime.h"
#include "SpoutBPFunctionLibrary.h"
#include "SpoutModule.h"

// -----------------------------------------------------------------------------
// Por que este puente se hizo en C++ y no en Blueprint (encargo explicito del
// usuario, que no quiere cablear nodos a mano) -- dos razones tecnicas reales,
// verificadas leyendo el plugin, no supuestas:
//
// 1) SpoutBPFunctionLibrary.h:110-116 (firma real):
//        static bool SpoutReceiver(FName SpoutName, UMaterialInterface* InputMaterial,
//            FName TextureParameterName, UMaterialInstanceDynamic*& OutMat,
//            UTexture2D*& OutTexture, UTextureRenderTarget2D* OptionalOutputRenderTarget = nullptr);
//
//    SpoutReceiver.cpp:436 solo crea la Dynamic Material Instance
//    "if (!OutMat && InputMaterial)". Desde Blueprint, OutMat es un pin de
//    salida sin memoria entre llamadas: llega null en cada Tick salvo que se
//    promueva a variable Y ademas se vuelva a pasar esa misma variable como
//    entrada -- un error facil de cometer wireando a mano, y exactamente el
//    motivo por el que el usuario prefirio no hacerlo a mano. En C++, OutMat
//    se respalda en el miembro UPROPERTY() DynamicMaterial: se le pasa de
//    vuelta en cada llamada, asi que SpoutReceiver ve el puntero no nulo
//    despues de la primera vez y reutiliza la misma instancia en vez de
//    crear una Dynamic Material Instance nueva cada frame.
//
// 2) OptionalOutputRenderTarget si se usa de verdad en SpoutReceiver.cpp:457-466
//    (redimensiona el destino, captura su recurso, y se lo pasa tanto a
//    ReceiveOnRenderThread_GPU como a ReceiveOnRenderThread_CPU) -- el
//    comentario de SpoutBPFunctionLibrary.cpp que dice "reserved for future
//    GPU-side copy paths" esta desactualizado respecto de la implementacion
//    real. No lo usa esta clase (no hace falta un render target aparte: el
//    material dinamico ya alimenta MI_Domo directamente), pero queda anotado
//    aqui para quien lo retome despues no se guie por ese comentario viejo.
// -----------------------------------------------------------------------------

ASpoutDomeReceiver::ASpoutDomeReceiver()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;

	// Nada de SceneComponent propio: este actor no tiene presencia visual
	// propia, solo alimenta el material de otra malla (TargetMeshComponent).
}

bool ASpoutDomeReceiver::ShouldTickIfViewportsOnly() const
{
	// Ver el comentario en el .h: esto es lo que hace que Tick() corra en el
	// viewport del editor sin necesidad de Play.
	return true;
}

void ASpoutDomeReceiver::BeginPlay()
{
	Super::BeginPlay();
}

void ASpoutDomeReceiver::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// Blindaje contra el crash de ERROR_MOD_NOT_FOUND (ver SpoutModule.h):
	// si Spout.dll no se pudo cargar en este proceso, ni siquiera se intenta
	// llamar a SpoutReceiver (que terminaria disparando la construccion de
	// SpoutDirectX dentro de FSpoutD3DContext::Initialize). El actor se
	// apaga solo -- deja de tickear -- y lo dice una sola vez: preferible
	// una cupula negra a arriesgar el editor.
	if (!FSpoutModule::IsSpoutRuntimeAvailable())
	{
		UE_LOG(LogTemp, Error,
			TEXT("ASpoutDomeReceiver (%s): Spout.dll no esta disponible en este proceso. ")
			TEXT("Este actor deja de tickear (cupula sin senal en vez de arriesgar el editor). ")
			TEXT("Revisar Saved/Logs por 'LogSpoutPlugin' para el motivo real, y ")
			TEXT("04_Docs/Unreal_sala_domo.md."),
			*GetName());
		SetActorTickEnabled(false);
		return;
	}

	if (!TargetMaterial)
	{
		return;
	}

	UMaterialInstanceDynamic* OutMat = DynamicMaterial;
	UTexture2D* OutTexture = ReceivedTexture;

	const bool bReceived = USpoutBPFunctionLibrary::SpoutReceiver(
		SpoutSenderName,
		TargetMaterial,
		TextureParameterName,
		OutMat,
		OutTexture);

	if (!bReceived)
	{
		// Tolerante a que el sender todavia no exista (TouchDesigner puede
		// no estar corriendo, o el nivel se abre antes que dosis.45.toe).
		// Un aviso cada tanto, no uno por Tick -- podrian ser mas de 90 por
		// segundo.
		const double Now = FPlatformTime::Seconds();
		if (Now - LastUnavailableWarningTime > 5.0)
		{
			UE_LOG(LogTemp, Warning,
				TEXT("ASpoutDomeReceiver (%s): sender Spout '%s' no disponible todavia."),
				*GetName(), *SpoutSenderName.ToString());
			LastUnavailableWarningTime = Now;
		}
		return;
	}

	ReceivedTexture = OutTexture;

	// OutMat solo cambia de puntero la primera vez que se recibe con exito
	// (ver el comentario de arriba): a partir de ahi es el mismo objeto en
	// cada llamada, asi que el material solo se vuelve a aplicar a la malla
	// cuando de verdad cambia -- no en cada frame.
	if (OutMat && DynamicMaterial != OutMat)
	{
		DynamicMaterial = OutMat;
		ApplyMaterialToMesh();
	}
}

void ASpoutDomeReceiver::ApplyMaterialToMesh()
{
	if (TargetMeshComponent && DynamicMaterial)
	{
		TargetMeshComponent->SetMaterial(TargetMaterialSlot, DynamicMaterial);
	}
}

void ASpoutDomeReceiver::ReaplicarMaterial()
{
	if (DynamicMaterial)
	{
		ApplyMaterialToMesh();
	}
	else if (TargetMeshComponent && TargetMaterial)
	{
		TargetMeshComponent->SetMaterial(TargetMaterialSlot, TargetMaterial);
	}
}
