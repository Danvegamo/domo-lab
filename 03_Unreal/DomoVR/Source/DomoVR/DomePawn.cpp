#include "DomePawn.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "DomeMediaController.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"

namespace
{
	constexpr float RadioCapsula = 34.f;
	/** Distancia entre los ojos y lo alto de la cabeza. */
	constexpr float OjosBajoCabeza = 10.f;
}

ADomeGameMode::ADomeGameMode()
{
	DefaultPawnClass = ADomePawn::StaticClass();
}

ADomePawn::ADomePawn()
{
	PrimaryActorTick.bCanEverTick = true;

	bUseControllerRotationYaw = true;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	GetCapsuleComponent()->InitCapsuleSize(RadioCapsula, (AlturaOjosActual + OjosBajoCabeza) * 0.5f);

	Camara = CreateDefaultSubobject<UCameraComponent>(TEXT("Camara"));
	Camara->SetupAttachment(GetCapsuleComponent());
	Camara->SetRelativeLocation(FVector(0.f, 0.f, (AlturaOjosActual + OjosBajoCabeza) * 0.5f - OjosBajoCabeza));
	Camara->bUsePawnControlRotation = true;

	UCharacterMovementComponent* Mov = GetCharacterMovement();
	Mov->MaxWalkSpeed = VelocidadCaminar;
	Mov->MaxFlySpeed = VelocidadVuelo;
	Mov->BrakingDecelerationWalking = 2500.f;
	Mov->BrakingDecelerationFlying = 2500.f;
	Mov->GroundFriction = 10.f;
	Mov->JumpZVelocity = 0.f;
	Mov->SetWalkableFloorAngle(50.f);
}

void ADomePawn::BeginPlay()
{
	Super::BeginPlay();
	if (const ADomeMediaController* C = ADomeMediaController::Buscar(GetWorld()))
	{
		AplicarAjustes(C->Controles);
	}
	else
	{
		AsentarEnElPiso();
	}
}

void ADomePawn::PonerAltura(float Altura)
{
	Altura = FMath::Clamp(Altura, 60.f, 260.f);
	UCapsuleComponent* Capsula = GetCapsuleComponent();
	const float Anterior = Capsula->GetUnscaledCapsuleHalfHeight();
	const float Nueva = (Altura + OjosBajoCabeza) * 0.5f;
	AlturaOjosActual = Altura;
	if (FMath::IsNearlyEqual(Anterior, Nueva))
	{
		return;
	}
	Capsula->SetCapsuleSize(RadioCapsula, Nueva);
	// Los pies se quedan donde estaban.
	AddActorWorldOffset(FVector(0.f, 0.f, Nueva - Anterior), false, nullptr, ETeleportType::TeleportPhysics);
	Camara->SetRelativeLocation(FVector(0.f, 0.f, Nueva - OjosBajoCabeza));
}

void ADomePawn::AplicarAjustes(const FDomeControles& K)
{
	VelocidadCaminar = K.VelocidadCaminar;
	VelocidadVuelo = K.VelocidadVuelo;
	MultiplicadorCorrer = K.MultiplicadorCorrer;
	Sensibilidad = K.Sensibilidad;
	bClicDerecho = K.bMirarSoloConClicDerecho;
	GetCharacterMovement()->GravityScale = K.Gravedad;
	PonerAltura(K.AlturaOjos);
	PonerModo(K.Modo);
}

void ADomePawn::PonerModo(EDomeModoMovimiento Nuevo)
{
	ModoActual = Nuevo;
	UCharacterMovementComponent* Mov = GetCharacterMovement();
	if (Nuevo == EDomeModoMovimiento::Caminar)
	{
		SetActorEnableCollision(true);
		Mov->SetMovementMode(MOVE_Falling);
		AsentarEnElPiso();
	}
	else
	{
		SetActorEnableCollision(Nuevo == EDomeModoMovimiento::Volar);
		Mov->SetMovementMode(MOVE_Flying);
		Mov->Velocity = FVector::ZeroVector;
	}
}

void ADomePawn::AsentarEnElPiso()
{
	UWorld* Mundo = GetWorld();
	if (!Mundo)
	{
		return;
	}
	const float Mitad = GetCapsuleComponent()->GetUnscaledCapsuleHalfHeight();
	const FVector Pos = GetActorLocation();
	FHitResult Golpe;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(DomoPiso), true, this);
	const FVector Desde(Pos.X, Pos.Y, Pos.Z + 400.f);
	const FVector Hasta(Pos.X, Pos.Y, Pos.Z - 3000.f);
	if (Mundo->LineTraceSingleByChannel(Golpe, Desde, Hasta, ECC_Visibility, Params))
	{
		SetActorLocation(FVector(Pos.X, Pos.Y, Golpe.ImpactPoint.Z + Mitad + 2.f), false, nullptr, ETeleportType::TeleportPhysics);
		bAsentado = true;
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("DomePawn: no hay piso bajo %s; el jugador queda donde esta."), *Pos.ToString());
	}
}

void ADomePawn::IrAOjos(const FVector& Ubicacion, const FRotator& Rotacion)
{
	if (ModoActual == EDomeModoMovimiento::Caminar)
	{
		PonerModo(EDomeModoMovimiento::Volar);
	}
	const float Mitad = GetCapsuleComponent()->GetUnscaledCapsuleHalfHeight();
	SetActorLocation(Ubicacion - FVector(0.f, 0.f, Mitad - OjosBajoCabeza), false, nullptr, ETeleportType::TeleportPhysics);
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->SetControlRotation(Rotacion);
	}
	GetCharacterMovement()->Velocity = FVector::ZeroVector;
}

void ADomePawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	APlayerController* PC = Cast<APlayerController>(GetController());
	ADomeMediaController* C = ADomeMediaController::Buscar(GetWorld());
	if (!PC || !C)
	{
		return;
	}
	const FDomeControles& K = C->Controles;
	const bool bEsperandoTecla = C->EstaEsperandoTecla();

	// --- Mirar ---
	float dx = 0.f, dy = 0.f;
	PC->GetInputMouseDelta(dx, dy);
	const bool bMirar = !C->MenuVisible() || !bClicDerecho || PC->IsInputKeyDown(EKeys::RightMouseButton);
	if (bMirar && (dx != 0.f || dy != 0.f))
	{
		FRotator R = PC->GetControlRotation();
		R.Yaw += dx * Sensibilidad;
		R.Pitch = FMath::Clamp(FRotator::NormalizeAxis(R.Pitch) + dy * Sensibilidad, -89.f, 89.f);
		PC->SetControlRotation(R);
	}

	// --- Moverse ---
	if (bEsperandoTecla)
	{
		return;
	}
	const float Adelante = (K.Apretada(EDomeAccion::Adelante, PC) ? 1.f : 0.f) - (K.Apretada(EDomeAccion::Atras, PC) ? 1.f : 0.f);
	const float Derecha = (K.Apretada(EDomeAccion::Derecha, PC) ? 1.f : 0.f) - (K.Apretada(EDomeAccion::Izquierda, PC) ? 1.f : 0.f);
	const float Arriba = (K.Apretada(EDomeAccion::Subir, PC) ? 1.f : 0.f) - (K.Apretada(EDomeAccion::Bajar, PC) ? 1.f : 0.f);
	const float Correr = K.Apretada(EDomeAccion::Correr, PC) ? MultiplicadorCorrer : 1.f;

	UCharacterMovementComponent* Mov = GetCharacterMovement();
	Mov->MaxWalkSpeed = VelocidadCaminar * Correr;
	Mov->MaxFlySpeed = VelocidadVuelo * Correr;

	const FRotator Giro = PC->GetControlRotation();
	FVector Dir = FVector::ZeroVector;
	if (ModoActual == EDomeModoMovimiento::Caminar)
	{
		const FRotator SoloYaw(0.f, Giro.Yaw, 0.f);
		Dir = FRotationMatrix(SoloYaw).GetUnitAxis(EAxis::X) * Adelante + FRotationMatrix(SoloYaw).GetUnitAxis(EAxis::Y) * Derecha;
	}
	else
	{
		Dir = FRotationMatrix(Giro).GetUnitAxis(EAxis::X) * Adelante + FRotationMatrix(Giro).GetUnitAxis(EAxis::Y) * Derecha
			+ FVector::UpVector * Arriba;
	}
	if (!Dir.IsNearlyZero())
	{
		AddMovementInput(Dir.GetClampedToMaxSize(1.f), 1.f);
	}
}
