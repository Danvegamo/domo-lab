#include "AbismoEscena.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "DomeEmisorNDI.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "ProceduralMeshComponent.h"

DEFINE_LOG_CATEGORY_STATIC(LogAbismo, Log, All);

AAbismoEscena::AAbismoEscena()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;

	USceneComponent* Raiz = CreateDefaultSubobject<USceneComponent>(TEXT("Raiz"));
	SetRootComponent(Raiz);

	Lecho = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Lecho"));
	Lecho->SetupAttachment(Raiz);
	Lecho->bUseAsyncCooking = false;
	Lecho->SetCastShadow(true);

	Nieve = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Nieve"));
	Nieve->SetupAttachment(Raiz);
	Nieve->SetCastShadow(false);
	Nieve->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	// Las particulas se reubican en el shader (envuelven alrededor de la camara); el recorte por caja
	// de cada instancia no las ve donde estan de verdad, asi que no se recortan.
	Nieve->bNeverDistanceCull = true;
	Nieve->SetCullDistances(0, 0);
}

// ---------------------------------------------------------------------------- relieve

float AAbismoEscena::AlturaEn(float X, float Y) const
{
	// Todo en coordenadas del lecho, en metros, con un desfase por semilla.
	const float Sx = X * 0.01f + Semilla * 13.7f;
	const float Sy = Y * 0.01f - Semilla * 7.3f;
	// Dunas largas: cordones que serpentean (1 - |sin| da crestas afiladas y valles suaves).
	const float Onda = Sx * 0.05f + 2.4f * FMath::PerlinNoise2D(FVector2D(Sx * 0.02f, Sy * 0.02f));
	const float Dunas = 1.f - FMath::Abs(FMath::Sin(Onda * PI * 2.f));
	// Colinas grandes y suaves.
	const float Colinas = FMath::PerlinNoise2D(FVector2D(Sx * 0.018f, Sy * 0.018f));
	// Afloramientos de roca: solo sobresale la parte positiva de un ruido mas fino.
	const float Roca = FMath::Max(0.f, FMath::PerlinNoise2D(FVector2D(Sx * 0.07f + 5.1f, Sy * 0.07f - 3.3f)) - 0.18f) * 2.6f;
	const float Grano = FMath::PerlinNoise2D(FVector2D(Sx * 0.5f, Sy * 0.5f)) * 0.04f;
	return NivelLecho + AlturaRelieve * (0.28f * Dunas + 0.55f * Colinas + 0.9f * Roca + Grano);
}

void AAbismoEscena::ConstruirLecho()
{
	const int32 N = Resolucion;
	const float Paso = LadoLecho / (N - 1);
	const float Mitad = LadoLecho * 0.5f;

	TArray<FVector> Vertices;
	TArray<FVector> Normales;
	TArray<FVector2D> UVs;
	TArray<FColor> Colores;
	TArray<FProcMeshTangent> Tangentes;
	TArray<int32> Triangulos;
	Vertices.Reserve(N * N);
	Normales.Reserve(N * N);
	UVs.Reserve(N * N);
	Colores.Reserve(N * N);
	Triangulos.Reserve((N - 1) * (N - 1) * 6);

	const FVector Origen = GetActorLocation();
	for (int32 j = 0; j < N; ++j)
	{
		for (int32 i = 0; i < N; ++i)
		{
			const float X = -Mitad + i * Paso;
			const float Y = -Mitad + j * Paso;
			const float Z = AlturaEn(X + Origen.X, Y + Origen.Y);
			Vertices.Add(FVector(X, Y, Z - Origen.Z));
			// Normal por diferencias finitas.
			const float Hx = AlturaEn(X + Origen.X + Paso, Y + Origen.Y) - AlturaEn(X + Origen.X - Paso, Y + Origen.Y);
			const float Hy = AlturaEn(X + Origen.X, Y + Origen.Y + Paso) - AlturaEn(X + Origen.X, Y + Origen.Y - Paso);
			const FVector Normal = FVector(-Hx, -Hy, 2.f * Paso).GetSafeNormal();
			Normales.Add(Normal);
			UVs.Add(FVector2D(X / 400.f, Y / 400.f));
			// Arena en lo plano, roca oscura en lo empinado y en lo alto; un poco de variacion por punto.
			const float Pendiente = 1.f - Normal.Z;
			const float Roca = FMath::Clamp(Pendiente * 5.f + (Z - Origen.Z - NivelLecho) / (AlturaRelieve * 1.4f), 0.f, 1.f);
			const float Vari = 0.85f + 0.3f * FMath::PerlinNoise2D(FVector2D(X * 0.004f + 9.f, Y * 0.004f));
			const FLinearColor Arena(0.42f * Vari, 0.38f * Vari, 0.27f * Vari);
			const FLinearColor Piedra(0.10f, 0.12f, 0.14f);
			Colores.Add(FLinearColor::LerpUsingHSV(Arena, Piedra, Roca).ToFColor(false));
			Tangentes.Add(FProcMeshTangent(1.f, 0.f, 0.f));
		}
	}
	for (int32 j = 0; j < N - 1; ++j)
	{
		for (int32 i = 0; i < N - 1; ++i)
		{
			const int32 A = j * N + i;
			const int32 B = A + 1;
			const int32 C = A + N;
			const int32 D = C + 1;
			Triangulos.Append({ A, C, B, B, C, D });
		}
	}
	Lecho->CreateMeshSection(0, Vertices, Triangulos, Normales, UVs, Colores, Tangentes, false);
	if (UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Abismo/M_Lecho.M_Lecho")))
	{
		Lecho->SetMaterial(0, Mat);
	}
	UE_LOG(LogAbismo, Display, TEXT("Lecho: %d x %d vertices, %.0f m de lado."), N, N, LadoLecho / 100.f);
}

// ----------------------------------------------------------------------------- nieve

void AAbismoEscena::ConstruirNieve()
{
	UStaticMesh* Esfera = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Abismo/M_Nieve.M_Nieve"));
	if (!Esfera || !Mat || CantidadNieve <= 0)
	{
		UE_LOG(LogAbismo, Warning, TEXT("Sin nieve marina: falta la esfera basica o /Game/Abismo/M_Nieve (correr crear_abismo.ps1)."));
		return;
	}
	Nieve->SetStaticMesh(Esfera);
	MatNieve = UMaterialInstanceDynamic::Create(Mat, this);
	MatNieve->SetScalarParameterValue(TEXT("Caja"), CajaNieve);
	Nieve->SetMaterial(0, MatNieve);

	FRandomStream Azar(Semilla);
	TArray<FTransform> Instancias;
	Instancias.Reserve(CantidadNieve);
	// Las instancias se reparten en una caja del tamano de la de envoltura; el shader las mueve junto a la camara.
	for (int32 i = 0; i < CantidadNieve; ++i)
	{
		const FVector P(Azar.FRandRange(-0.5f, 0.5f) * CajaNieve, Azar.FRandRange(-0.5f, 0.5f) * CajaNieve, Azar.FRandRange(-0.5f, 0.5f) * CajaNieve);
		// Esfera basica: 100 cm de diametro. Motas de 0,4 a 2,2 cm; unas pocas mas grandes que brillan mas.
		const float Grande = Azar.FRand() < 0.04f ? 2.5f : 1.f;
		const float Escala = Azar.FRandRange(0.006f, 0.03f) * Grande;
		Instancias.Add(FTransform(FRotator::ZeroRotator, P, FVector(Escala)));
	}
	Nieve->AddInstances(Instancias, false);
}

// ------------------------------------------------------------------------- atmosfera

void AAbismoEscena::ConstruirAtmosfera()
{
	UWorld* Mundo = GetWorld();
	if (!Mundo) { return; }

	// Niebla: el agua. Densa, azul verdosa, con la luz de la superficie dispersandose en ella.
	AExponentialHeightFog* Niebla = Mundo->SpawnActor<AExponentialHeightFog>(FVector(0.f, 0.f, NivelLecho + 500.f), FRotator::ZeroRotator);
	if (Niebla && Niebla->GetComponent())
	{
		UExponentialHeightFogComponent* F = Niebla->GetComponent();
		F->SetFogDensity(DensidadNiebla);
		F->SetFogHeightFalloff(0.0015f);
		F->SetFogInscatteringColor(ColorAgua * 3.f);
		F->SetStartDistance(0.f);
		F->SetFogMaxOpacity(0.995f);
		F->SetVolumetricFog(true);
		F->SetVolumetricFogDistance(9000.f);
		F->SetVolumetricFogScatteringDistribution(0.55f);
		F->SetVolumetricFogExtinctionScale(1.f);
		F->SetVolumetricFogAlbedo(FColor(120, 190, 220));
		F->SetDirectionalInscatteringColor(FLinearColor(0.15f, 0.45f, 0.6f));
		F->SetDirectionalInscatteringExponent(6.f);
	}

	// La luz que baja desde la superficie: azul, inclinada, con sombras suaves.
	ADirectionalLight* Sol = Mundo->SpawnActor<ADirectionalLight>(FVector(0.f, 0.f, 3000.f), FRotator(-62.f, 35.f, 0.f));
	if (Sol && Sol->GetLightComponent())
	{
		UDirectionalLightComponent* L = Cast<UDirectionalLightComponent>(Sol->GetLightComponent());
		L->SetMobility(EComponentMobility::Movable);
		L->SetIntensity(2.2f);
		L->SetLightColor(FLinearColor(0.35f, 0.75f, 1.f));
		L->SetCastVolumetricShadow(true);
		L->SetVolumetricScatteringIntensity(2.5f);
		L->SetAtmosphereSunLight(false);
	}

	// Posproceso: brillo alto, grano de color frio, sin exposicion automatica.
	APostProcessVolume* PP = Mundo->SpawnActor<APostProcessVolume>();
	if (PP)
	{
		PP->bUnbound = true;
		FPostProcessSettings& S = PP->Settings;
		S.bOverride_BloomIntensity = true;
		S.BloomIntensity = IntensidadGlow;
		S.bOverride_BloomThreshold = true;
		S.BloomThreshold = 0.6f;
		S.bOverride_AutoExposureMethod = true;
		S.AutoExposureMethod = EAutoExposureMethod::AEM_Histogram;
		S.bOverride_AutoExposureMinBrightness = true;
		S.AutoExposureMinBrightness = 0.9f;
		S.bOverride_AutoExposureMaxBrightness = true;
		S.AutoExposureMaxBrightness = 0.9f;
		S.bOverride_DynamicGlobalIlluminationMethod = true;
		S.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::None;
		S.bOverride_ReflectionMethod = true;
		S.ReflectionMethod = EReflectionMethod::None;
		S.bOverride_VignetteIntensity = true;
		S.VignetteIntensity = 0.f;
	}
}

// ------------------------------------------------------------------------------ ciclo

void AAbismoEscena::BeginPlay()
{
	Super::BeginPlay();
	FString Texto;
	int32 Numero = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoSemilla="), Numero)) { Semilla = Numero; }
	ConstruirLecho();
	ConstruirNieve();
	ConstruirAtmosfera();
	for (TActorIterator<ADomeEmisorNDI> It(GetWorld()); It; ++It) { Emisor = *It; break; }
	if (!Emisor) { UE_LOG(LogAbismo, Warning, TEXT("No hay ADomeEmisorNDI en el nivel: la nieve no sigue a la camara.")); }
}

void AAbismoEscena::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	if (!MatNieve) { return; }
	FVector Camara = FVector::ZeroVector;
	if (Emisor)
	{
		Camara = Emisor->PosicionOjo();
	}
	else if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		FRotator Rot;
		PC->GetPlayerViewPoint(Camara, Rot);
	}
	MatNieve->SetVectorParameterValue(TEXT("Camara"), FLinearColor(Camara.X, Camara.Y, Camara.Z, 0.f));
}
