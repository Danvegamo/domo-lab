// Jugador del ejecutable: un Character que camina sobre el piso de la sala.
//
// El DefaultPawn del motor vuela en la direccion de la mirada y no choca con
// nada, asi que al mirar hacia abajo y avanzar se cae uno del piso. Este pawn
// tiene tres modos (Caminar con gravedad y colisiones, Volar sin gravedad y
// Fantasma sin colisiones), altura de ojos, velocidades y sensibilidad
// ajustables, y lee las teclas de FDomeControles (remapeables desde el menu).

#pragma once

#include "CoreMinimal.h"
#include "DomeControles.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "DomePawn.generated.h"

class UCameraComponent;

UCLASS()
class DOMOVR_API ADomePawn : public ACharacter
{
	GENERATED_BODY()

public:
	ADomePawn();

	/** Aplica los ajustes de movimiento (velocidades, gravedad, altura de ojos, modo). */
	void AplicarAjustes(const FDomeControles& Controles);

	void PonerModo(EDomeModoMovimiento Nuevo);

	/** Pone los ojos en Ubicacion (no los pies) mirando hacia Rotacion. En Caminar pasa a Volar
	 *  para que la gravedad no lo baje del punto de vista. */
	void IrAOjos(const FVector& Ubicacion, const FRotator& Rotacion);

	/** Apoya los pies en el piso bajo la ubicacion actual (traza hacia abajo). */
	void AsentarEnElPiso();

	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Domo")
	TObjectPtr<UCameraComponent> Camara;

protected:
	virtual void BeginPlay() override;

private:
	EDomeModoMovimiento ModoActual = EDomeModoMovimiento::Caminar;
	float AlturaOjosActual = 160.f;
	float VelocidadCaminar = 250.f;
	float VelocidadVuelo = 700.f;
	float MultiplicadorCorrer = 2.5f;
	float Sensibilidad = 0.12f;
	bool bClicDerecho = true;
	bool bAsentado = false;

	void PonerAltura(float Altura);
};

/** Modo de juego del proyecto: usa ADomePawn en vez del DefaultPawn. */
UCLASS()
class DOMOVR_API ADomeGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ADomeGameMode();
};
