// Reproductor de video de la cupula, sin TouchDesigner.
//
// ADomeMediaController lee una lista de cues (Movies/playlist.json), abre cada
// video con Media Framework (MP_Domo -> MT_Domo) y lo pone en la cupula a
// traves de MI_DomoMedia, un material que hace por pixel lo mismo que la
// cadena de TouchDesigner (orientar.frag + domo_mapping.frag +
// pantalla169.frag, al reves). Convive con ASpoutDomeReceiver: el parametro
// Fuente elige quien alimenta la cupula. Ver 04_Docs/06_Unreal_standalone.md.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DomeMediaController.generated.h"

class UFileMediaSource;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UMediaPlayer;
class UMediaSoundComponent;
class UMediaTexture;
class UStaticMeshComponent;
class ASpoutDomeReceiver;

/** Como viene el video. Los numeros son los que lee el material (parametro Formato). */
UENUM(BlueprintType)
enum class EDomeFormato : uint8
{
	Equirect360 = 0 UMETA(DisplayName = "360 equirectangular"),
	Domemaster = 1 UMETA(DisplayName = "Domemaster (fisheye 180)"),
	VR180 = 2 UMETA(DisplayName = "VR180 mono"),
	VR180SBS = 3 UMETA(DisplayName = "VR180 lado a lado"),
	Plano169 = 4 UMETA(DisplayName = "Plano (16:9) en una pantalla")
};

/** Quien alimenta la cupula. */
UENUM(BlueprintType)
enum class EDomeFuente : uint8
{
	Spout UMETA(DisplayName = "Spout (TouchDesigner)"),
	Media UMETA(DisplayName = "Media (videos de la playlist)")
};

/** El mapping de la pagina Mapping de TouchDesigner. */
USTRUCT(BlueprintType)
struct FDomeMapping
{
	GENERATED_BODY()

	/** Corre el cenit, en fraccion del domemaster. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float CentroX = 0.f;

	/** Corre el cenit; positivo lo lleva hacia atras y mete piso adelante. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float CentroY = 0.f;

	/** Menor que 1 mete mas grados en el circulo; mayor que 1 acerca. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Escala = 1.f;

	/** Gira el domemaster, en grados (positivo, antihorario). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Rotar = 0.f;
};

/** Una pantalla plana sobre la cupula (formato Plano169, pantalla169.frag). */
USTRUCT(BlueprintType)
struct FDomePantalla
{
	GENERATED_BODY()

	/** Azimut del centro, grados (0 al frente, + a la derecha). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Azimut = 0.f;

	/** Elevacion del centro, grados (0 horizonte, 90 cenit). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Elevacion = 30.f;

	/** Ancho angular, grados. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Ancho = 100.f;

	/** Alto angular, grados. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Alto = 56.f;

	/** false = plana (gnomonica, rectas rectas); true = curva (angulos iguales). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool bCurva = false;

	/** Borde suave, fraccion del ancho de la pantalla. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Borde = 0.02f;
};

/** Un cue de la playlist: un video y como se pone en la cupula. */
USTRUCT(BlueprintType)
struct FDomeCue
{
	GENERATED_BODY()

	/** Nombre para mostrar; si falta, el nombre del archivo. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FString Nombre;

	/** Ruta del video, relativa a la carpeta de la playlist o absoluta. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FString Archivo;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	EDomeFormato Formato = EDomeFormato::Equirect360;

	/** Giro esferico del lienzo (orientar.frag), grados. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Yaw = 0.f;

	/** Positivo lleva el frente del contenido hacia el cenit. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Pitch = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Roll = 0.f;

	/** Elevacion a la que queda el horizonte del video, con el cenit fijo (grados, max 80). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Horizonte = 0.f;

	/** Reparto de la compresion de Horizonte (1 = pareja). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Curva = 1.f;

	/** FOV del contenido, grados. 0 = el de la sala (Fovauto de TouchDesigner). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float FovContenido = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FDomeMapping Mapping;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FDomePantalla Pantalla;

	/** Volumen del audio del video (0 a 1 o mas). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Volumen = 1.f;

	/** true: el video se repite. false: al terminar pasa al siguiente cue (si bAutoAvanzar). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool Loop = true;
};

UCLASS(ClassGroup = (Domo), config = Game)
class DOMOVR_API ADomeMediaController : public AActor
{
	GENERATED_BODY()

public:
	ADomeMediaController();

	// --- Referencias (las pone crear_media_domo.py) ---------------------------

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Referencias")
	TObjectPtr<UMediaPlayer> MediaPlayer;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Referencias")
	TObjectPtr<UMediaTexture> MediaTexture;

	/** MI_DomoMedia: de ella se crea la instancia dinamica que va en la cupula. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Referencias")
	TObjectPtr<UMaterialInterface> MediaMaterial;

	/** El StaticMeshComponent de Domo_Actor. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Referencias")
	TObjectPtr<UStaticMeshComponent> TargetMeshComponent;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Referencias")
	int32 TargetMaterialSlot = 0;

	/** El receptor de Spout del nivel; se apaga mientras la fuente es Media. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Referencias")
	TObjectPtr<ASpoutDomeReceiver> SpoutReceiver;

	/** Audio del video: no espacial, suena igual en toda la sala. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Domo|Referencias")
	TObjectPtr<UMediaSoundComponent> MediaSound;

	// --- Operacion ------------------------------------------------------------

	/** Spout (TouchDesigner en vivo) o Media (la playlist). Se cambia en vivo.
	 *  Es la fuente del editor (y de Play en el editor): los niveles se guardan
	 *  en Spout. Fuera del editor (build empaquetado, -game) manda
	 *  FuenteFueraDelEditor, y -DomoFuente=Spout|Media pisa a las dos. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	EDomeFuente Fuente = EDomeFuente::Spout;

	/** Fuente con la que arranca el build empaquetado (y -game): Media, la
	 *  version sin TouchDesigner. Se cambia con
	 *  [/Script/DomoVR.DomeMediaController] FuenteFueraDelEditor=Spout en
	 *  Config/DefaultGame.ini (o en el Game.ini del build). */
	UPROPERTY(Config, EditAnywhere, Category = "Domo")
	EDomeFuente FuenteFueraDelEditor = EDomeFuente::Media;

	/** Playlist, relativa a Content/ (en el build, <build>/DomoVR/Content/). La
	 *  sobreescriben, en este orden: -DomoPlaylist=<ruta> en la linea de
	 *  comandos, y en el editor RutaPlaylistEditor del ini. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FString PlaylistPath = TEXT("Movies/playlist.json");

	/** Ruta absoluta de la playlist solo para el editor
	 *  ([/Script/DomoVR.DomeMediaController] RutaPlaylistEditor= en
	 *  Config/DefaultGame.ini o en Saved/Config/.../Game.ini). Vacia = PlaylistPath. */
	UPROPERTY(Config, EditAnywhere, Category = "Domo")
	FString RutaPlaylistEditor;

	/** FOV de la sala (el de la cupula). Las tres salas del repo son de 180. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float FovSala = 180.f;

	/** Multiplica la emision del video (el EmissiveIntensity de M_Domo). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Brillo = 1.f;

	/** Al terminar un cue sin Loop, pasa solo al siguiente. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool bAutoAvanzar = true;

	/** Segundos del fundido a negro (y del audio) de Blackout. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float SegundosFundido = 0.5f;

	/** Reproducir tambien en el viewport del editor sin Play (en silencio). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool bReproducirEnEditor = true;

	/** Teclas en runtime: flechas o PageUp/PageDown = cue, B o punto = negro,
	 *  espacio = pausa, Inicio = reiniciar cue, S = Spout/Media, 1-9 = cue, F1 = ayuda. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool bControlTeclado = true;

	/** Reproductor de Media Framework a forzar. WmfMedia por defecto; vacio = automatico. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FName Reproductor = FName(TEXT("WmfMedia"));

	/** Los cues cargados de la playlist (solo lectura; se editan en el JSON). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Domo")
	TArray<FDomeCue> Cues;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Domo")
	int32 CueActual = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Domo")
	bool bNegro = false;

	// --- Funciones para Blueprint, Remote Control y consola ---------------------

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void Play();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void Pause();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void TogglePause();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void Next();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void Prev();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void GoToCue(int32 Indice);

	/** Vuelve al principio del cue actual. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	void Reiniciar();

	/** Cambia en vivo un parametro del material (Yaw, Pitch, Roll, Horizonte,
	 *  Curva, FovContenido, CentroX, CentroY, Escala, Rotar, Formato, Brillo,
	 *  PantallaAzimut, ...). Vale hasta el proximo cambio de cue. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	void SetParam(FName Nombre, float Valor);

	/** Fundido a negro (true) o de vuelta (false), imagen y audio. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	void Blackout(bool bActivar);

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void ToggleBlackout();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void SetFuente(EDomeFuente NuevaFuente);

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void ToggleFuente();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	bool RecargarPlaylist();

	UFUNCTION(BlueprintPure, Category = "Domo")
	FString GetNombreCue(int32 Indice) const;

	/** Linea de estado para el log y la pantalla. */
	UFUNCTION(BlueprintPure, Category = "Domo")
	FString DescribirEstado() const;

	/** Preset de calidad: "VR" (liviano, el de fabrica del proyecto) o
	 *  "Render" (capturas: 200 % de resolucion con TSR, Lumen con hit
	 *  lighting). Tambien domo.Preset y -DomoPreset=Render. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	static bool AplicarPreset(const FString& Nombre);

	//~ Begin AActor interface
	virtual void Tick(float DeltaSeconds) override;
	virtual bool ShouldTickIfViewportsOnly() const override;
#if WITH_EDITOR
	virtual void PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent) override;
#endif
	//~ End AActor interface

	/** Primer controlador del mundo (para los comandos de consola domo.*). */
	static ADomeMediaController* Buscar(UWorld* World);

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UFileMediaSource> FuenteArchivo;

	bool bInicializado = false;
	bool bCueAbierto = false;
	bool bPendienteAvanzar = false;
	float AlfaNegro = 0.f;
	double UltimoReintento = 0.0;
	FString CarpetaPlaylist;

	/** Guion de prueba (-DomoGuion=archivo): comandos de consola con "esperar N". */
	TArray<FString> Guion;
	int32 LineaGuion = 0;
	float EsperaGuion = 0.f;

	bool EstaActivo() const;
	bool EsMundoDeJuego() const;
	void Inicializar();
	FString ResolverRutaPlaylist() const;
	bool CargarPlaylist(const FString& Ruta);
	void AbrirCue(int32 Indice);
	void AplicarParametros(const FDomeCue& Cue);
	void AplicarFuente();
	void AsegurarMaterialEnCupula();
	void ActualizarNegroYVolumen(float DeltaSeconds);
	void ConfigurarTeclado();
	void Mensaje(const FString& Texto, float Segundos = 3.f) const;
	void CorrerGuion(float DeltaSeconds);

	UFUNCTION()
	void AlTerminarVideo();

	UFUNCTION()
	void AlFallarApertura(FString Url);

	// Teclas (sin parametros, para BindKey).
	void TeclaSiguiente() { Next(); }
	void TeclaAnterior() { Prev(); }
	void TeclaNegro() { ToggleBlackout(); }
	void TeclaPausa() { TogglePause(); }
	void TeclaReiniciar() { Reiniciar(); }
	void TeclaFuente() { ToggleFuente(); }
	void TeclaAyuda();
	void TeclaCue(int32 Indice) { GoToCue(Indice); }
};
