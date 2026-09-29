#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AbismoFauna.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class AAbismoEscena;
class ADomeEmisorNDI;

/** Como se mueve cada especie. */
UENUM()
enum class EAbismoMovimiento : uint8
{
	Nadar,     // rumbo propio, cambia de direccion despacio, se mantiene a una altura sobre el lecho
	Cardumen,  // grupos que siguen a un lider y se abren y cierran alrededor de el
	Flotar,    // a la deriva, sube y baja despacio y gira sobre si misma
	Fijo,      // parada sobre el lecho
};

/** Organico: luz propia y late en el dialogo. Plastico: responde con luz sintetica. Decorado: roca, coral y alga. */
UENUM()
enum class EAbismoTipo : uint8
{
	Organico,
	Plastico,
	Decorado,
};

/**
 * La fauna del abismo y el dialogo con la basura plastica.
 *
 * Coloca por codigo las criaturas (mezclas de la Colombia actual con el Cretacico de Villa de Leyva) y los
 * desechos del Antropoceno sobre el lecho de AAbismoEscena. Cada especie es un InstancedStaticMesh: los
 * cuerpos nadan con un shader (sin esqueleto) y el codigo solo mueve los cuerpos enteros.
 *
 * El dialogo dura un ciclo (`DuracionDialogo`): calma, las criaturas llaman con ondas de luz, la basura
 * responde con una luz sintetica, las criaturas se acercan a ella y todo vuelve a la calma. Ver
 * 04_Docs/09_Abismo_Unreal_a_NDI.md.
 *
 * Las mallas salen de 01_Blender/generar_criaturas.py y se importan con 03_Unreal/crear_abismo.py.
 */
UCLASS()
class AAbismoFauna : public AActor
{
	GENERATED_BODY()

public:
	AAbismoFauna();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo")
	int32 Semilla = 1957;

	/** Radio (cm) del area donde vive la fauna, alrededor de `Centro`. Tiene que cubrir el recorrido de la camara. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo")
	float RadioArea = 4400.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo")
	FVector Centro = FVector(0.f, 0.f, 0.f);

	/** Segundos que dura una vuelta completa del dialogo. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Dialogo", meta = (ClampMin = "20"))
	float DuracionDialogo = 75.f;

	/** Multiplica la cantidad de todas las especies (0 = ninguna, 1 = la tabla). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo", meta = (ClampMin = "0", ClampMax = "3"))
	float Densidad = 1.f;

	/** Cuanto se acercan las criaturas a la basura cuando le responde (0 = nada). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo|Dialogo", meta = (ClampMin = "0", ClampMax = "2"))
	float Curiosidad = 1.f;

	/** Cuantas veces se ve la malla al reves; poner en verdadero si las criaturas nadan de cola. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Abismo")
	bool bMallasAlReves = false;

	/** Estado del dialogo, de 0 a 1 (lo leen la escena y los shaders). */
	UFUNCTION(BlueprintPure, Category = "Abismo|Dialogo")
	float NivelPulso() const { return Pulso; }

	UFUNCTION(BlueprintPure, Category = "Abismo|Dialogo")
	float NivelRespuesta() const { return Respuesta; }

	/** Salta el dialogo al segundo indicado del ciclo (para capturas). */
	UFUNCTION(BlueprintCallable, Category = "Abismo|Dialogo")
	void IrAlDialogo(float Segundo) { RelojDialogo = Segundo; }

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

private:
	struct FEspecie
	{
		const TCHAR* Id;
		EAbismoTipo Tipo;
		EAbismoMovimiento Movimiento;
		int32 Cantidad;
		float EscalaMin, EscalaMax;
		float Velocidad;           // cm/s
		float AlturaMin, AlturaMax;  // sobre el lecho, cm
		float AmpRelativa;         // amplitud del nado, como fraccion del largo
		float VelNado;             // ciclos por segundo del nado
		FVector Lado;              // direccion en que se doblan las puntas moviles
		FLinearColor Brillo;       // color del borde de luz
		FRotator RotMalla;         // para poner la malla en su sitio (el alga se para)
		float Grupo;               // en cardumen: cuantos por grupo
	};

	struct FBicho
	{
		FVector Posicion = FVector::ZeroVector;
		FVector Direccion = FVector::ForwardVector;
		float Velocidad = 0.f;
		float Escala = 1.f;
		float Fase = 0.f;
		float Deriva = 0.f;   // semilla de sus cambios de rumbo
		float Altura = 0.f;   // altura que busca sobre el lecho
		int32 Grupo = 0;
		FVector Giro = FVector::ZeroVector;  // velocidad de giro propia (grados/s), para lo que rueda
		FRotator Orientacion = FRotator::ZeroRotator;
		FVector PosObjetivo = FVector::ZeroVector;  // el desecho al que se acerca en el dialogo
		bool bTieneObjetivo = false;
		float TiempoEncuentro = 0.f;  // > 0: nada hacia PosEncuentro, delante de la camara, para que se le vea de cerca
		FVector PosEncuentro = FVector::ZeroVector;
	};

	struct FGrupoEspecie
	{
		const FEspecie* Especie = nullptr;
		UInstancedStaticMeshComponent* ISM = nullptr;
		UMaterialInstanceDynamic* Mat = nullptr;
		TArray<FBicho> Bichos;
		FVector Extension = FVector(100.f);  // caja de la malla, cm
	};

	struct FOnda
	{
		FVector Posicion = FVector::ZeroVector;
		float Edad = 1.f;      // 0 nace, 1 se apaga
		float Duracion = 5.f;
		float Radio = 1500.f;
	};

	static const TArray<FEspecie>& Tabla();

	TArray<FGrupoEspecie> Grupos;
	TArray<FOnda> Ondas;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> OndasISM;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> OndasMat;
	UPROPERTY() TArray<TObjectPtr<UInstancedStaticMeshComponent>> ComponentesISM;
	UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materiales;
	UPROPERTY() TObjectPtr<AAbismoEscena> Escena;
	UPROPERTY() TObjectPtr<ADomeEmisorNDI> Emisor;

	FRandomStream Azar;
	float Reloj = 0.f;
	float RelojDialogo = 0.f;
	float Pulso = 0.f;
	float Respuesta = 0.f;
	float Curiosa = 0.f;
	float ProximaOnda = 4.f;
	float ProximoObjetivo = 0.f;
	float ProximoEncuentro = 8.f;

	void Construir();
	void ActualizarDialogo(float Delta);
	void MoverGrupo(FGrupoEspecie& G, float Delta);
	void EscribirTransformaciones(FGrupoEspecie& G);
	void LanzarOndas();
	void BuscarObjetivos();
	void ProgramarEncuentro();
	float AlturaLecho(float X, float Y) const;
	FVector PosicionCamara() const;
};
