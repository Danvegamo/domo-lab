#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/EngineTypes.h"
#include "DomeEmisorNDI.generated.h"

class USceneCaptureComponentCube;
class UTextureRenderTargetCube;
class UTextureRenderTarget2D;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UMediaCapture;
class UNDIMediaOutput;
class SWidget;

/**
 * El sentido inverso del proyecto: Unreal genera el domo y TouchDesigner (o el proyector) lo recibe.
 *
 * Coloca una camara de 360 grados (SceneCaptureComponentCube), la convierte a un domemaster fisheye
 * con el material M_CuboADomemaster (el mismo formato que saca TouchDesigner: el cenit al centro, el
 * frente abajo) y lo manda por NDI con el plugin NDIMedia que trae el motor. En TouchDesigner llega
 * por un NDI In (ver 04_Docs/09_Abismo_Unreal_a_NDI.md).
 *
 * El actor tambien es la camara: recorre un camino suave (una curva de Lissajous alrededor de
 * `Centro`) con el frente hacia donde avanza, y `InclinacionDomo` inclina el cenit de la cupula hacia
 * adelante para que el lecho quede dentro de la semiesfera que la cupula muestra.
 */
UCLASS()
class ADomeEmisorNDI : public AActor
{
	GENERATED_BODY()

public:
	ADomeEmisorNDI();

	// ------------------------------------------------------------------ salida

	/** Lado de cada cara del cubo (px). 1024 (11 px por grado, igual que un domemaster de 2048) da 40 a 50 cuadros por segundo en la 3090; 1536 baja a 25 a 30. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida", meta = (ClampMin = "256", ClampMax = "4096"))
	int32 LadoCubo = 1024;

	/** Lado del domemaster que se manda por NDI (px, cuadrado). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida", meta = (ClampMin = "512", ClampMax = "4096"))
	int32 LadoDomemaster = 2048;

	/** Grados de la cupula: 180 es una semiesfera; mas de 180 mete lo que hay bajo el horizonte de la cupula. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida", meta = (ClampMin = "90", ClampMax = "270"))
	float FovDomo = 180.f;

	/** Nombre de la fuente NDI que se ve en TouchDesigner (NDI In). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida")
	FString NombreNDI = TEXT("Unreal_Abismo");

	/** Cuadros por segundo que se anuncian por NDI. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida", meta = (ClampMin = "10", ClampMax = "120"))
	int32 FpsNDI = 30;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida")
	bool bEnviarNDI = true;

	/** Brillo fijo de la exposicion (sube o baja toda la imagen; 1 = referencia). Se ajusta a ojo con -AbismoExposicion=. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida", meta = (ClampMin = "0.01"))
	float Exposicion = 0.9f;

	/** 0 domemaster normal; 1 degradado de UV; 2 direccion como color (diagnostico del material). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida")
	int32 ModoDepuracion = 0;

	/** El material que convierte el cubo a domemaster. Si es nulo se carga /Game/Abismo/M_CuboADomemaster. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Salida")
	TObjectPtr<UMaterialInterface> MaterialDomemaster;

	// ------------------------------------------------------------------ camara

	/** Cuanto se inclina el cenit de la cupula hacia donde avanza la camara (0 = mira hacia arriba, 90 = mira al frente). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Camara", meta = (ClampMin = "0", ClampMax = "90"))
	float InclinacionDomo = 50.f;

	/** Si es verdadero, la camara recorre el camino de abajo; si no, se queda donde esta el actor. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Camara")
	bool bRecorrido = true;

	/** Centro del recorrido, en cm. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Camara")
	FVector Centro = FVector(0.f, 0.f, 380.f);

	/** Semiejes del recorrido (cm): cuanto se aleja del centro en X, Y y Z. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Camara")
	FVector Radios = FVector(3200.f, 2400.f, 140.f);

	/** Un ciclo completo del recorrido, en segundos. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Camara", meta = (ClampMin = "10"))
	float DuracionCiclo = 240.f;

	/** Balanceo lento (grados) que se suma al frente para que la camara no vaya sobre rieles. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Camara")
	float Balanceo = 6.f;

	/** 1 = velocidad normal; 0 detiene el recorrido. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Camara", meta = (ClampMin = "0", ClampMax = "4"))
	float Velocidad = 1.f;

	// ------------------------------------------------------------- vista previa

	/** Muestra el domemaster en la ventana (tecla F4 lo alterna). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Vista previa")
	bool bVistaPrevia = true;

	UFUNCTION(BlueprintCallable, Category = "Domo|Salida")
	void PonerVistaPrevia(bool bMostrar);

	/** Tiempo del recorrido en segundos (lo usa la escena para sincronizar sus efectos con la camara). */
	UFUNCTION(BlueprintPure, Category = "Domo|Camara")
	float TiempoRecorrido() const { return Reloj; }

	/** Posicion del ojo de la camara. */
	UFUNCTION(BlueprintPure, Category = "Domo|Camara")
	FVector PosicionOjo() const;

	/** Guarda el domemaster actual como PNG (diagnostico y capturas). Devuelve verdadero si escribio el archivo. */
	UFUNCTION(BlueprintCallable, Category = "Domo|Salida")
	bool GuardarFoto(const FString& Ruta);

	/** Salta el recorrido al segundo indicado (para capturar el mismo cuadro una y otra vez). */
	UFUNCTION(BlueprintCallable, Category = "Domo|Camara")
	void IrAlSegundo(float Segundos) { Reloj = Segundos; }

	/** Direccion en que avanza la camara (unitaria). */
	UFUNCTION(BlueprintPure, Category = "Domo|Camara")
	FVector DireccionAvance() const { return Avance; }

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Motivo) override;
	virtual void Tick(float DeltaTime) override;

private:
	UPROPERTY(VisibleAnywhere, Category = "Domo")
	TObjectPtr<USceneCaptureComponentCube> Captura;

	UPROPERTY(Transient)
	TObjectPtr<UTextureRenderTargetCube> RTCubo;

	UPROPERTY(Transient)
	TObjectPtr<UTextureRenderTarget2D> RTDomemaster;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MatDomemaster;

	UPROPERTY(Transient)
	TObjectPtr<UNDIMediaOutput> SalidaNDI;

	UPROPERTY(Transient)
	TObjectPtr<UMediaCapture> CapturaNDI;

	// Capturas automaticas por linea de comandos: -AbismoFoto=Ruta.png[;Ruta2.png] -AbismoFotoCada=8 -AbismoSalir
	TArray<FString> FotosAuto;
	float FotoCada = 8.f;
	float ProximaFoto = -1.f;
	float RelojReal = 0.f;
	int32 FotosHechas = 0;
	bool bSalirAlFinal = false;

	int32 CuadrosCaptura = 0;
	float AcumFps = 0.f;
	int32 CuadrosFps = 0;
	float Reloj = 0.f;
	FVector Avance = FVector::ForwardVector;
	FVector AvanceSuave = FVector::ForwardVector;
	TSharedPtr<SWidget> VistaPreviaWidget;
	TSharedPtr<struct FSlateBrush> VistaPreviaPincel;
	bool bF4Antes = false;

	void PrepararRenderTargets();
	void IniciarNDI();
	void ColocarCamara(float Delta);
	FVector PuntoDelRecorrido(float T) const;
	void MostrarVistaPrevia(bool bMostrar);
};
