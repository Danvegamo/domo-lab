// Actor que recibe la senal de Spout de TouchDesigner y la aplica en vivo
// sobre la malla de la cupula, en C++ (no en Blueprint). Ver el .cpp para
// las dos razones tecnicas del cambio (material dinamico recreado cada
// frame desde Blueprint, y la firma real de SpoutReceiver).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SpoutDomeReceiver.generated.h"

class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;
class UTexture2D;

UCLASS(ClassGroup = (Spout))
class DOMOVR_API ASpoutDomeReceiver : public AActor
{
	GENERATED_BODY()

public:
	ASpoutDomeReceiver();

	/** Nombre del sender de Spout a recibir. Tiene que coincidir exactamente
	 *  con el "Sender Name" que publica TouchDesigner (nodo Syphon Spout Out).
	 *  Se puede cambiar en cualquier momento desde el panel de detalles, sin
	 *  tocar codigo ni recompilar. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Spout")
	FName SpoutSenderName = FName(TEXT("TDSyphonSpoutOut"));

	/** Material base (normalmente una Material Instance, p. ej. MI_Domo) a
	 *  partir del cual SpoutReceiver crea una Dynamic Material Instance. Debe
	 *  tener un parametro de textura con el nombre de TextureParameterName. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Spout")
	TObjectPtr<UMaterialInterface> TargetMaterial;

	/** Nombre del parametro de textura expuesto en TargetMaterial. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Spout")
	FName TextureParameterName = FName(TEXT("SpoutTexture"));

	/** Componente de malla al que se le aplica el material dinamico (el
	 *  StaticMeshComponent del actor de la cupula, SM_Domo). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Spout")
	TObjectPtr<UStaticMeshComponent> TargetMeshComponent;

	/** Slot de material del TargetMeshComponent donde va el material dinamico. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Spout")
	int32 TargetMaterialSlot = 0;

	//~ Begin AActor interface
	virtual void Tick(float DeltaSeconds) override;
	/** Devuelve true a proposito: es lo que hace que este actor tambien
	 *  tickee en el viewport del editor (fuera de PIE). Ver Actor.cpp,
	 *  FActorTickFunction::ExecuteTick, linea ~376: cuando el tipo de tick es
	 *  LEVELTICK_ViewportsOnly (el que usa el editor sin Play), solo tickean
	 *  los actores cuyo ShouldTickIfViewportsOnly() devuelva true. Por
	 *  defecto en AActor devuelve false. Este es el mecanismo real de UE
	 *  5.8 para esto -- no bRunConstructionScriptOnDrag (eso es para
	 *  Construction Script, que corre una vez al mover/soltar el actor, no
	 *  cada frame) ni un Tick de UActorComponent con bTickInEditor (eso
	 *  tickea el componente, no el Tick() del Actor). */
	virtual bool ShouldTickIfViewportsOnly() const override;
	//~ End AActor interface

protected:
	virtual void BeginPlay() override;

private:
	/** Material dinamico devuelto por SpoutReceiver. Se guarda con
	 *  UPROPERTY() por dos razones: (1) que el recolector de basura no lo
	 *  recoja mientras esta en uso, y (2) que se le pueda seguir pasando de
	 *  vuelta a SpoutReceiver en cada llamada -- la propia implementacion de
	 *  SpoutReceiver (SpoutReceiver.cpp) solo crea una instancia nueva
	 *  "if (!OutMat && InputMaterial)": si se le sigue pasando el mismo
	 *  puntero no nulo, reutiliza el que ya existe en vez de crear uno
	 *  nuevo. Llamado desde Blueprint, el pin de salida no tiene memoria
	 *  entre llamadas (llega null cada vez si no se promueve a variable, y
	 *  aun promovido a variable local no persiste igual que un UPROPERTY de
	 *  este actor), asi que crearia una Dynamic Material Instance nueva en
	 *  cada Tick -- ese es el bug real que esta clase evita. */
	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;

	/** Textura transitoria devuelta por SpoutReceiver (la misma se reutiliza
	 *  frame a frame; se guarda para pasarla de vuelta igual que el
	 *  material). */
	UPROPERTY()
	TObjectPtr<UTexture2D> ReceivedTexture;

	/** Ultimo momento (segundos de plataforma) en el que se aviso en el log
	 *  que el sender no esta disponible. Evita llenar el log con un aviso
	 *  por frame (podrian ser mas de 90 por segundo) cuando TouchDesigner
	 *  todavia no publico el sender o se cerro. */
	double LastUnavailableWarningTime = 0.0;

	void ApplyMaterialToMesh();
};
