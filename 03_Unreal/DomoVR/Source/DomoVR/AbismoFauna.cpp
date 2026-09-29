#include "AbismoFauna.h"

#include "AbismoEscena.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "DomeEmisorNDI.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

DEFINE_LOG_CATEGORY_STATIC(LogFauna, Log, All);

namespace
{
	float Suave(float A, float B, float X)
	{
		const float T = FMath::Clamp((X - A) / FMath::Max(B - A, 1e-4f), 0.f, 1.f);
		return T * T * (3.f - 2.f * T);
	}

	float Ruido(float T, float Semilla)
	{
		return FMath::PerlinNoise2D(FVector2D(T, Semilla * 0.37f + 0.11f));
	}
}

// Una fila por especie. Los datos reales de cada criatura (que cruza, que fosil o especie la inspira) estan en
// 04_Docs/08_Criaturas_abismo.md; aqui solo lo que hace falta para colocarla y moverla.
const TArray<AAbismoFauna::FEspecie>& AAbismoFauna::Tabla()
{
	using M = EAbismoMovimiento;
	using T = EAbismoTipo;
	static const TArray<FEspecie> Filas = {
		// Id, Tipo, Movimiento, Cantidad, Escala min/max, Velocidad, Altura min/max, Amp, VelNado, Lado, Brillo, RotMalla, Grupo
		{ TEXT("kronos_jaguar"),   T::Organico,  M::Nadar,    5, 1.1f, 1.6f,  95.f, 350.f,  900.f, 0.06f, 0.30f, FVector(0, 1, 0),      FLinearColor(1.0f, 0.55f, 0.15f), FRotator::ZeroRotator, 1.f },
		{ TEXT("calla_manati"),    T::Organico,  M::Nadar,    4, 1.0f, 1.4f,  70.f, 300.f,  800.f, 0.05f, 0.25f, FVector(0, 0.4f, 1),   FLinearColor(0.3f, 0.8f, 1.0f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("desma_orquidea"),  T::Organico,  M::Nadar,    5, 1.1f, 1.6f,   45.f, 250.f,  700.f, 0.04f, 0.22f, FVector(0, 0.3f, 1),   FLinearColor(0.9f, 0.3f, 0.9f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("kyhy_inia"),       T::Organico,  M::Nadar,    6, 1.0f, 1.5f,  135.f, 300.f, 1100.f, 0.07f, 0.55f, FVector(0, 0, 1),      FLinearColor(1.0f, 0.4f, 0.7f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("amonita_rana"),    T::Organico,  M::Flotar,  14, 0.8f, 1.7f,   28.f, 200.f, 1200.f, 0.10f, 0.50f, FVector(0, 1, 0.6f),   FLinearColor(1.0f, 0.9f, 0.1f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("belemnita_morpho"),T::Organico,  M::Cardumen, 240, 0.8f, 1.4f, 115.f, 250.f, 1300.f, 0.18f, 1.10f, FVector(0, 0, 1),     FLinearColor(0.1f, 0.4f, 1.0f),   FRotator::ZeroRotator, 24.f },
		{ TEXT("bolsa_plastica"),  T::Plastico,  M::Flotar,  45, 1.0f, 2.6f,   14.f, 150.f, 1400.f, 0.20f, 0.35f, FVector(0, 1, 1),      FLinearColor(0.6f, 0.8f, 1.0f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("botella_pet"),     T::Plastico,  M::Flotar,  28, 2.0f, 3.0f,   10.f, 120.f, 1200.f, 0.f,    0.f,   FVector(0, 1, 0),      FLinearColor(0.6f, 0.8f, 1.0f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("anillo_lata"),     T::Plastico,  M::Flotar,  36, 3.0f, 5.0f,   12.f, 120.f, 1200.f, 0.f,    0.f,   FVector(0, 1, 0),      FLinearColor(0.6f, 0.8f, 1.0f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("red_fantasma"),    T::Plastico,  M::Flotar,   6, 1.5f, 3.0f,    9.f, 250.f,  900.f, 0.06f, 0.15f, FVector(0, 1, 0.5f),   FLinearColor(0.6f, 0.9f, 0.7f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("roca_lecho"),      T::Decorado,  M::Fijo,    46, 1.5f, 6.0f,    0.f,   0.f,    0.f, 0.f,    0.f,   FVector(0, 1, 0),      FLinearColor(0.2f, 0.7f, 0.9f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("coral_abanico"),   T::Decorado,  M::Fijo,    90, 1.0f, 3.2f,    0.f,   0.f,    0.f, 0.02f, 0.2f,  FVector(0, 1, 0),      FLinearColor(1.0f, 0.3f, 0.5f),   FRotator::ZeroRotator, 1.f },
		{ TEXT("kelp_tira"),       T::Decorado,  M::Fijo,   170, 1.0f, 2.4f,    0.f,   0.f,    0.f, 0.10f, 0.3f,  FVector(0, 1, 0),      FLinearColor(0.8f, 0.7f, 0.2f),   FRotator(90.f, 0.f, 0.f), 1.f },
	};
	return Filas;
}

AAbismoFauna::AAbismoFauna()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	USceneComponent* Raiz = CreateDefaultSubobject<USceneComponent>(TEXT("Raiz"));
	SetRootComponent(Raiz);
}

FVector AAbismoFauna::PosicionCamara() const
{
	return Emisor ? Emisor->PosicionOjo() : Centro;
}

float AAbismoFauna::AlturaLecho(float X, float Y) const
{
	return Escena ? Escena->AlturaEn(X, Y) : 0.f;
}

void AAbismoFauna::Construir()
{
	UStaticMesh* Esfera = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	UMaterialInterface* MBase[3] = {
		LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Abismo/M_Criatura.M_Criatura")),
		LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Abismo/M_Plastico.M_Plastico")),
		LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Abismo/M_Decorado.M_Decorado")),
	};
	UMaterialInterface* MOnda = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Abismo/M_Onda.M_Onda"));

	auto NuevoISM = [this](UStaticMesh* Malla, int32 CustomData) -> UInstancedStaticMeshComponent*
	{
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(this);
		C->SetupAttachment(GetRootComponent());
		C->RegisterComponent();
		C->SetStaticMesh(Malla);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->bNeverDistanceCull = true;
		C->SetCullDistances(0, 0);
		C->NumCustomDataFloats = CustomData;
		ComponentesISM.Add(C);
		return C;
	};

	for (const FEspecie& E : Tabla())
	{
		const int32 N = FMath::RoundToInt(E.Cantidad * Densidad);
		if (N <= 0) { continue; }
		const FString Ruta = FString::Printf(TEXT("/Game/Abismo/Criaturas/SM_%s.SM_%s"), E.Id, E.Id);
		UStaticMesh* Malla = LoadObject<UStaticMesh>(nullptr, *Ruta);
		if (!Malla)
		{
			UE_LOG(LogFauna, Warning, TEXT("Falta %s: correr 03_Unreal/crear_abismo.ps1."), *Ruta);
			continue;
		}
		FGrupoEspecie G;
		G.Especie = &E;
		G.Extension = Malla->GetBounds().BoxExtent * 2.f;
		G.ISM = NuevoISM(Malla, 2);
		UMaterialInterface* Base = MBase[static_cast<int32>(E.Tipo)];
		if (Base)
		{
			G.Mat = UMaterialInstanceDynamic::Create(Base, this);
			const float Largo = G.Extension.X;
			G.Mat->SetScalarParameterValue(TEXT("Amp"), Largo * E.AmpRelativa);
			G.Mat->SetScalarParameterValue(TEXT("Onda"), 2.f * PI / FMath::Max(Largo * 0.9f, 1.f));
			G.Mat->SetVectorParameterValue(TEXT("Eje"), FLinearColor(1.f, 0.f, 0.f, 0.f));
			G.Mat->SetVectorParameterValue(TEXT("Lado"), FLinearColor(E.Lado.X, E.Lado.Y, E.Lado.Z, 0.f));
			G.Mat->SetVectorParameterValue(TEXT("GlowColor"), E.Brillo);
			G.ISM->SetMaterial(0, G.Mat);
			Materiales.Add(G.Mat);
		}
		G.ISM->SetCastShadow(E.Tipo == EAbismoTipo::Decorado);

		TArray<FTransform> Instancias;
		for (int32 i = 0; i < N; ++i)
		{
			FBicho B;
			const float Ang = Azar.FRand() * 2.f * PI;
			const float Rad = FMath::Sqrt(Azar.FRand()) * RadioArea;
			B.Posicion = Centro + FVector(FMath::Cos(Ang) * Rad, FMath::Sin(Ang) * Rad, 0.f);
			B.Altura = Azar.FRandRange(E.AlturaMin, E.AlturaMax);
			const float Lecho = AlturaLecho(B.Posicion.X, B.Posicion.Y);
			B.Posicion.Z = E.Movimiento == EAbismoMovimiento::Fijo ? Lecho - 0.06f * G.Extension.Z : Lecho + B.Altura;
			B.Direccion = FRotator(0.f, Azar.FRand() * 360.f, 0.f).Vector();
			B.Escala = Azar.FRandRange(E.EscalaMin, E.EscalaMax);
			B.Velocidad = E.Velocidad * Azar.FRandRange(0.8f, 1.2f);
			B.Fase = Azar.FRand();
			B.Deriva = Azar.FRand() * 200.f;
			B.Grupo = FMath::FloorToInt(i / FMath::Max(E.Grupo, 1.f));
			B.Giro = FVector(Azar.FRandRange(-25.f, 25.f), Azar.FRandRange(-25.f, 25.f), Azar.FRandRange(-40.f, 40.f));
			B.Orientacion = B.Direccion.Rotation();
			if (E.Movimiento == EAbismoMovimiento::Fijo) { B.Orientacion = FRotator(0.f, Azar.FRand() * 360.f, 0.f); }
			G.Bichos.Add(B);
			Instancias.Add(FTransform(B.Orientacion, B.Posicion, FVector(B.Escala)));
		}
		G.ISM->AddInstances(Instancias, false);
		for (int32 i = 0; i < N; ++i)
		{
			G.ISM->SetCustomDataValue(i, 0, G.Bichos[i].Fase, false);
			G.ISM->SetCustomDataValue(i, 1, E.VelNado * Azar.FRandRange(0.85f, 1.15f), i == N - 1);
		}
		Grupos.Add(MoveTemp(G));
		UE_LOG(LogFauna, Display, TEXT("%s: %d instancias."), E.Id, N);
	}

	// Ondas de luz con que las criaturas "hablan": un grupo pequeno de esferas que se agrandan y se apagan.
	if (Esfera && MOnda)
	{
		OndasISM = NuevoISM(Esfera, 1);
		OndasMat = UMaterialInstanceDynamic::Create(MOnda, this);
		OndasISM->SetMaterial(0, OndasMat);
		Ondas.SetNum(12);
		TArray<FTransform> Inst;
		for (int32 i = 0; i < Ondas.Num(); ++i) { Inst.Add(FTransform(FRotator::ZeroRotator, FVector(0.f, 0.f, -100000.f), FVector(0.001f))); }
		OndasISM->AddInstances(Inst, false);
	}
}

void AAbismoFauna::BeginPlay()
{
	Super::BeginPlay();
	int32 N = 0;
	float F = 0.f;
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoSemilla="), N)) { Semilla = N; }
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoDensidad="), F)) { Densidad = F; }
	if (FParse::Value(FCommandLine::Get(), TEXT("AbismoDialogo="), F)) { RelojDialogo = F; }
	Azar.Initialize(Semilla);
	for (TActorIterator<AAbismoEscena> It(GetWorld()); It; ++It) { Escena = *It; break; }
	for (TActorIterator<ADomeEmisorNDI> It(GetWorld()); It; ++It) { Emisor = *It; break; }
	if (Escena) { Centro = FVector(Escena->GetActorLocation().X, Escena->GetActorLocation().Y, 0.f); }
	Construir();
}

// -------------------------------------------------------------------------------- dialogo

void AAbismoFauna::ActualizarDialogo(float Delta)
{
	RelojDialogo += Delta;
	const float U = FMath::Fmod(RelojDialogo, DuracionDialogo) / DuracionDialogo;
	// calma | llamada de las criaturas | respuesta de la basura | acercamiento | calma
	Pulso = 0.08f + 0.92f * (Suave(0.25f, 0.33f, U) - Suave(0.60f, 0.75f, U));
	Respuesta = Suave(0.38f, 0.50f, U) - Suave(0.86f, 0.98f, U);
	// La curiosidad (acercarse a la basura) empieza cuando la basura ya respondio.
	Curiosa = (Suave(0.42f, 0.52f, U) - Suave(0.82f, 0.92f, U)) * Curiosidad;

	for (FGrupoEspecie& G : Grupos)
	{
		if (!G.Mat) { continue; }
		if (G.Especie->Tipo == EAbismoTipo::Organico) { G.Mat->SetScalarParameterValue(TEXT("Pulso"), Pulso); }
		else if (G.Especie->Tipo == EAbismoTipo::Plastico) { G.Mat->SetScalarParameterValue(TEXT("Respuesta"), Respuesta); }
	}

	// Durante la llamada, cada pocos segundos las criaturas grandes mas cercanas a la camara sueltan una onda.
	if (U > 0.25f && U < 0.44f)
	{
		ProximaOnda -= Delta;
		if (ProximaOnda <= 0.f) { LanzarOndas(); ProximaOnda = 2.6f; }
	}
	ProximoObjetivo -= Delta;
	if (ProximoObjetivo <= 0.f) { BuscarObjetivos(); ProximoObjetivo = 2.f; }
	ProximoEncuentro -= Delta;
	if (ProximoEncuentro <= 0.f) { ProgramarEncuentro(); ProximoEncuentro = 18.f; }

	if (OndasISM)
	{
		TArray<FTransform> Inst;
		Inst.Reserve(Ondas.Num());
		for (int32 i = 0; i < Ondas.Num(); ++i)
		{
			FOnda& O = Ondas[i];
			if (O.Edad < 1.f)
			{
				O.Edad += Delta / O.Duracion;
				const float Radio = FMath::Lerp(60.f, O.Radio, FMath::Sqrt(FMath::Clamp(O.Edad, 0.f, 1.f)));
				Inst.Add(FTransform(FRotator::ZeroRotator, O.Posicion, FVector(Radio / 50.f)));
				OndasISM->SetCustomDataValue(i, 0, FMath::Clamp(O.Edad, 0.f, 1.f), false);
			}
			else
			{
				Inst.Add(FTransform(FRotator::ZeroRotator, FVector(0.f, 0.f, -100000.f), FVector(0.001f)));
			}
		}
		OndasISM->BatchUpdateInstancesTransforms(0, Inst, true, true, true);
	}
}

void AAbismoFauna::LanzarOndas()
{
	const FVector Cam = PosicionCamara();
	// Las tres criaturas nadadoras mas cercanas a la camara.
	TArray<TPair<float, FVector>> Cerca;
	for (const FGrupoEspecie& G : Grupos)
	{
		if (G.Especie->Tipo != EAbismoTipo::Organico || G.Especie->Movimiento != EAbismoMovimiento::Nadar) { continue; }
		for (const FBicho& B : G.Bichos) { Cerca.Add(TPair<float, FVector>(FVector::DistSquared(B.Posicion, Cam), B.Posicion)); }
	}
	Cerca.Sort([](const TPair<float, FVector>& A, const TPair<float, FVector>& B) { return A.Key < B.Key; });
	int32 Lanzadas = 0;
	for (const TPair<float, FVector>& P : Cerca)
	{
		if (Lanzadas >= 3) { break; }
		for (FOnda& O : Ondas)
		{
			if (O.Edad >= 1.f)
			{
				O.Posicion = P.Value;
				O.Edad = 0.f;
				O.Duracion = 5.5f;
				O.Radio = 2200.f;
				++Lanzadas;
				break;
			}
		}
	}
}

void AAbismoFauna::ProgramarEncuentro()
{
	// De vez en cuando una criatura grande cruza por delante de la camara, a unos 6 a 12 m, para que se la vea entera.
	if (!Emisor) { return; }
	TArray<FBicho*> Grandes;
	for (FGrupoEspecie& G : Grupos)
	{
		if (G.Especie->Tipo != EAbismoTipo::Organico || G.Especie->Movimiento != EAbismoMovimiento::Nadar) { continue; }
		for (FBicho& B : G.Bichos) { if (B.TiempoEncuentro <= 0.f) { Grandes.Add(&B); } }
	}
	if (Grandes.Num() == 0) { return; }
	FBicho* Elegida = Grandes[Azar.RandRange(0, Grandes.Num() - 1)];
	const FVector Cam = Emisor->PosicionOjo();
	const FVector Avance = Emisor->DireccionAvance();
	const FVector Lado = FVector::CrossProduct(FVector::UpVector, Avance).GetSafeNormal();
	const float Signo = Azar.FRand() < 0.5f ? -1.f : 1.f;
	Elegida->PosEncuentro = Cam + Avance * Azar.FRandRange(1500.f, 2400.f) + Lado * Signo * Azar.FRandRange(500.f, 900.f) + FVector(0.f, 0.f, Azar.FRandRange(-100.f, 250.f));
	Elegida->TiempoEncuentro = 14.f;
}

void AAbismoFauna::BuscarObjetivos()
{
	TArray<FVector> Basura;
	for (const FGrupoEspecie& G : Grupos)
	{
		if (G.Especie->Tipo != EAbismoTipo::Plastico) { continue; }
		for (const FBicho& B : G.Bichos) { Basura.Add(B.Posicion); }
	}
	if (Basura.Num() == 0) { return; }
	for (FGrupoEspecie& G : Grupos)
	{
		if (G.Especie->Tipo != EAbismoTipo::Organico || G.Especie->Movimiento != EAbismoMovimiento::Nadar) { continue; }
		for (FBicho& B : G.Bichos)
		{
			float Mejor = TNumericLimits<float>::Max();
			for (const FVector& P : Basura)
			{
				const float D = FVector::DistSquared(B.Posicion, P);
				if (D < Mejor) { Mejor = D; B.PosObjetivo = P; B.bTieneObjetivo = true; }
			}
		}
	}
}

// -------------------------------------------------------------------------------- movimiento

void AAbismoFauna::MoverGrupo(FGrupoEspecie& G, float Delta)
{
	const FEspecie& E = *G.Especie;
	if (E.Movimiento == EAbismoMovimiento::Fijo) { return; }
	const FVector Cam = PosicionCamara();

	for (int32 i = 0; i < G.Bichos.Num(); ++i)
	{
		FBicho& B = G.Bichos[i];
		const float T = Reloj * 0.12f + B.Deriva;

		if (E.Movimiento == EAbismoMovimiento::Nadar || (E.Movimiento == EAbismoMovimiento::Cardumen && (i % FMath::Max(1, FMath::RoundToInt(E.Grupo))) == 0))
		{
			FRotator R = B.Direccion.Rotation();
			const float GiroYaw = Ruido(T, 3.f) * 2.f * 32.f;
			R.Yaw += GiroYaw * Delta;
			R.Pitch += Ruido(T * 1.3f, 9.f) * 2.f * 7.f * Delta;
			// Altura sobre el lecho.
			const float Objetivo = AlturaLecho(B.Posicion.X, B.Posicion.Y) + B.Altura;
			R.Pitch += FMath::Clamp((Objetivo - B.Posicion.Z) * 0.02f, -1.f, 1.f) * 22.f * Delta;
			// Encuentro con la camara: mientras dura, manda sobre todo lo demas.
			if (B.TiempoEncuentro > 0.f)
			{
				B.TiempoEncuentro -= Delta;
				const FVector A = B.PosEncuentro - B.Posicion;
				if (A.Size() < 500.f) { B.TiempoEncuentro = 0.f; }
				else
				{
					const FRotator Deseado = A.Rotation();
					R.Yaw = FMath::FixedTurn(R.Yaw, Deseado.Yaw, 75.f * Delta);
					R.Pitch = FMath::FixedTurn(R.Pitch, Deseado.Pitch, 30.f * Delta);
				}
			}
			// Atraccion a la basura cuando ella responde: las criaturas giran hacia ella y la rodean a distancia.
			if (E.Tipo == EAbismoTipo::Organico && B.bTieneObjetivo && Curiosa > 0.02f && B.TiempoEncuentro <= 0.f)
			{
				const FVector A = B.PosObjetivo - B.Posicion;
				const float D = A.Size();
				if (D > 380.f)
				{
					const FRotator Deseado = A.Rotation();
					R.Yaw = FMath::FixedTurn(R.Yaw, Deseado.Yaw, 70.f * Curiosa * Delta);
					R.Pitch = FMath::FixedTurn(R.Pitch, Deseado.Pitch, 25.f * Curiosa * Delta);
				}
				else
				{
					// Ya cerca: girar alrededor, con la basura al costado.
					R.Yaw = FMath::FixedTurn(R.Yaw, A.Rotation().Yaw + 90.f, 60.f * Curiosa * Delta);
				}
			}
			// Quedarse en el area.
			const FVector AlCentro = Centro - B.Posicion;
			if (FVector2D(AlCentro.X, AlCentro.Y).Size() > RadioArea)
			{
				R.Yaw = FMath::FixedTurn(R.Yaw, FVector(AlCentro.X, AlCentro.Y, 0.f).Rotation().Yaw, 55.f * Delta);
			}
			// No pasar por encima de la camara: un desvio suave.
			const FVector DeCam = B.Posicion - Cam;
			if (DeCam.Size() < 450.f && B.TiempoEncuentro <= 0.f)
			{
				R.Yaw = FMath::FixedTurn(R.Yaw, DeCam.Rotation().Yaw, 90.f * Delta);
			}
			R.Pitch = FMath::Clamp(R.Pitch, -28.f, 28.f);
			R.Roll = FMath::FInterpTo(R.Roll, -FMath::Clamp(GiroYaw * 0.5f, -20.f, 20.f), Delta, 1.5f);
			B.Direccion = R.Vector();
			B.Posicion += B.Direccion * (B.Velocidad * Delta);
			B.Orientacion = R;
		}
		else if (E.Movimiento == EAbismoMovimiento::Cardumen)
		{
			const int32 Tam = FMath::Max(1, FMath::RoundToInt(E.Grupo));
			const FBicho& L = G.Bichos[(i / Tam) * Tam];
			const float Fx = B.Fase * 6.28f;
			const float Radio = 60.f + 210.f * B.Fase;
			const FVector Desvio = FVector(FMath::Sin(Reloj * 0.9f + Fx) * Radio, FMath::Sin(Reloj * 0.7f + Fx * 1.7f) * Radio, FMath::Sin(Reloj * 1.1f + Fx * 2.3f) * Radio * 0.6f);
			const FVector Meta = L.Posicion - L.Direccion * (80.f + 260.f * B.Fase) + Desvio;
			const FVector Antes = B.Posicion;
			B.Posicion = FMath::VInterpTo(B.Posicion, Meta, Delta, 2.2f);
			const FVector V = (B.Posicion - Antes) / FMath::Max(Delta, 1e-3f);
			if (V.SizeSquared() > 100.f) { B.Direccion = FMath::VInterpNormalRotationTo(B.Direccion, V.GetSafeNormal(), Delta, 180.f); }
			B.Orientacion = B.Direccion.Rotation();
		}
		else // Flotar
		{
			// A la deriva con una corriente comun, que sube y baja despacio; lo que rueda gira sobre si mismo.
			const FVector Corriente = FVector(0.85f, 0.45f, 0.f).GetSafeNormal() * B.Velocidad;
			B.Posicion += Corriente * Delta;
			B.Posicion.Z += FMath::Sin(Reloj * 0.35f + B.Fase * 6.28f) * 9.f * Delta;
			if (E.Tipo == EAbismoTipo::Organico)
			{
				// Las amonitas nadan despacio hacia donde apunta su concha, ademas de la corriente.
				B.Posicion += B.Direccion * (B.Velocidad * 0.5f * Delta);
				FRotator R = B.Direccion.Rotation();
				R.Yaw += Ruido(T, 5.f) * 2.f * 25.f * Delta;
				B.Direccion = R.Vector();
				B.Orientacion = R;
			}
			else
			{
				B.Orientacion += FRotator(B.Giro.X, B.Giro.Z, B.Giro.Y) * Delta * 0.4f;
			}
			const float Lecho = AlturaLecho(B.Posicion.X, B.Posicion.Y);
			B.Posicion.Z = FMath::Max(B.Posicion.Z, Lecho + 80.f);
			const FVector2D DeCentro(B.Posicion.X - Centro.X, B.Posicion.Y - Centro.Y);
			if (DeCentro.Size() > RadioArea)
			{
				// Al llegar al borde reaparece del lado contrario, donde la niebla ya lo tapa.
				const FVector2D Nuevo = -DeCentro * 0.96f;
				B.Posicion.X = Centro.X + Nuevo.X;
				B.Posicion.Y = Centro.Y + Nuevo.Y;
				B.Posicion.Z = AlturaLecho(B.Posicion.X, B.Posicion.Y) + B.Altura;
			}
		}
	}
}

void AAbismoFauna::EscribirTransformaciones(FGrupoEspecie& G)
{
	if (!G.ISM || G.Especie->Movimiento == EAbismoMovimiento::Fijo) { return; }
	TArray<FTransform> Inst;
	Inst.Reserve(G.Bichos.Num());
	const FQuat Malla = G.Especie->RotMalla.Quaternion() * (bMallasAlReves ? FRotator(0.f, 180.f, 0.f).Quaternion() : FQuat::Identity);
	for (const FBicho& B : G.Bichos)
	{
		Inst.Add(FTransform(B.Orientacion.Quaternion() * Malla, B.Posicion, FVector(B.Escala)));
	}
	G.ISM->BatchUpdateInstancesTransforms(0, Inst, true, true, true);
}

void AAbismoFauna::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const float Delta = FMath::Min(DeltaTime, 0.1f);
	Reloj += Delta;
	ActualizarDialogo(Delta);
	for (FGrupoEspecie& G : Grupos)
	{
		MoverGrupo(G, Delta);
		EscribirTransformaciones(G);
	}
}

// Comandos de consola para probar el dialogo sin esperar el ciclo.
static AAbismoFauna* PrimeraFauna(UWorld* Mundo)
{
	if (!Mundo) { return nullptr; }
	for (TActorIterator<AAbismoFauna> It(Mundo); It; ++It) { return *It; }
	return nullptr;
}

static FAutoConsoleCommandWithWorldAndArgs CmdAbismoDialogo(TEXT("abismo.Dialogo"),
	TEXT("abismo.Dialogo S: salta al segundo S del ciclo del dialogo (0 calma, 20 llamada, 35 respuesta, 55 acercamiento)."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* Mundo)
	{
		if (AAbismoFauna* F = PrimeraFauna(Mundo)) { if (Args.Num() > 0) { F->IrAlDialogo(FCString::Atof(*Args[0])); } }
	}));
