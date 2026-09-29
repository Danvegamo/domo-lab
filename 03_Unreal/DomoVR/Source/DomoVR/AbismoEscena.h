#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AbismoEscena.generated.h"

class UProceduralMeshComponent;
class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMesh;
class ADomeEmisorNDI;
class AExponentialHeightFog;
class ADirectionalLight;
class APostProcessVolume;

/**
 * El lecho marino del abismo, armado por codigo al empezar: relieve de dunas y rocas, nieve marina
 * (particulas que flotan alrededor de la camara), niebla azul verdosa, una luz que baja desde la
 * superficie y el posproceso con brillo (glow). Todo sale de una semilla, asi que el mismo numero da
 * siempre el mismo lecho.
 *
 * No necesita mallas ni texturas externas. Los materiales se crean con 03_Unreal/crear_abismo.py.
 * La fauna y la basura plastica las coloca AAbismoFauna, sobre este mismo lecho.
 */
UCLASS()
class AAbismoEscena : public AActor
{
	GENERATED_BODY()

public:
	AAbismoEscena();

	/** Misma semilla, mismo lecho. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo")
	int32 Semilla = 1957;

	/** Lado del lecho en cm. Tiene que cubrir el recorrido de la camara y algo mas. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Lecho", meta = (ClampMin = "2000"))
	float LadoLecho = 12000.f;

	/** Vertices por lado del lecho. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Lecho", meta = (ClampMin = "32", ClampMax = "512"))
	int32 Resolucion = 300;

	/** Cuanto suben las dunas y las rocas (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Lecho")
	float AlturaRelieve = 420.f;

	/** Altura del lecho promedio respecto del cero del mundo (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Lecho")
	float NivelLecho = 0.f;

	/** Cantidad de particulas de nieve marina. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Particulas", meta = (ClampMin = "0", ClampMax = "40000"))
	int32 CantidadNieve = 9000;

	/** Lado de la caja de particulas alrededor de la camara (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Particulas")
	float CajaNieve = 3600.f;

	/** Color base del glow de la niebla y de las particulas. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Atmosfera")
	FLinearColor ColorAgua = FLinearColor(0.004f, 0.045f, 0.085f, 1.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Atmosfera", meta = (ClampMin = "0"))
	float DensidadNiebla = 0.018f;

	/** Intensidad del brillo (bloom) del posproceso. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Atmosfera")
	float IntensidadGlow = 2.2f;

	/** Altura del lecho en (X, Y): la fauna lo usa para posarse o nadar a una altura fija sobre el fondo. */
	UFUNCTION(BlueprintCallable, Category = "Abismo")
	float AlturaEn(float X, float Y) const;

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

private:
	UPROPERTY(VisibleAnywhere, Category = "Abismo")
	TObjectPtr<UProceduralMeshComponent> Lecho;

	UPROPERTY(VisibleAnywhere, Category = "Abismo")
	TObjectPtr<UInstancedStaticMeshComponent> Nieve;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MatNieve;

	UPROPERTY(Transient)
	TObjectPtr<ADomeEmisorNDI> Emisor;

	void ConstruirLecho();
	void ConstruirNieve();
	void ConstruirAtmosfera();
};
