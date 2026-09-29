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
#include "DomeControles.h"
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
class FDomeMenu;
class FSocket;

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

/** Una fila de pantallas sobre la cupula (formato Plano169). Es una fila de la tabla
 *  `screens` de TouchDesigner (video_dome/screens_module.py): una pantalla que puede
 *  repetirse en anillo con las copias cosidas entre si. */
USTRUCT(BlueprintType)
struct FDomePantallaFila
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FString Nombre = TEXT("pantalla");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool bEncendida = true;

	/** 0 plana, 1 curva, 2 banda, 3 tunel, 4 cilindro. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	int32 Forma = 0;

	/** Azimut del centro, grados (0 al frente, + a la derecha). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Yaw = 0.f;

	/** Elevacion del centro, grados (0 horizonte, 90 cenit). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Elevacion = 45.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Roll = 0.f;

	/** Ancho y alto angulares, grados. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Ancho = 70.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Alto = 39.f;

	/** 0 no, 1 horizontal, 2 vertical, 3 ambos. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	int32 Espejo = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Opacidad = 1.f;

	/** Recorte del cuadro que usa la pantalla (fracciones 0 a 1). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float CropX = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float CropY = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float CropW = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float CropH = 1.f;

	/** Borde suave, fraccion de la pantalla. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Borde = 0.04f;

	/** Repeticiones del video dentro de la pantalla (banda, tunel, cilindro). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Repeticion = 1.f;

	/** Grados que se encima una copia con la siguiente. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Solape = 0.f;

	/** Copias en anillo (1 a 12) y el arco que ocupan, en grados. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	int32 Copias = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Arco = 360.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool bEspejoAlterno = false;

	/** Corrimiento del recorte por copia (mosaico). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Corrimiento = 0.f;

	/** Bordes que se degradan: 0 todos, 1 solo los costados, 2 solo arriba y abajo. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	int32 Bordes = 0;

	/** Cuanto le afecta el recorrido y el giro animados del cue. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Recorrido = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Giro = 0.f;
};

/** Capa de fondo de los montajes de pantallas (la pagina Fondo de VIDEO_DOME en TouchDesigner):
 *  el propio video, desenfocado, detras de las pantallas. */
USTRUCT(BlueprintType)
struct FDomeFondo
{
	GENERATED_BODY()

	/** 0 sin fondo (negro), 1 lavado (copia agrandada del cuadro), 2 envolvente (el cuadro da la vuelta al domo). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	int32 Modo = 2;

	/** Cuanto se desenfoca (equivale al tamano del Blur de TouchDesigner sobre 1080 px). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Desenfoque = 60.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Brillo = 0.35f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Saturacion = 0.7f;

	/** Zoom del lavado; tiene que ser al menos el aspecto del video (1,78 en 16:9). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Zoom = 1.8f;

	/** Repeticiones del envolvente alrededor del domo. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Repeticiones = 2.f;

	/** Giro del fondo, grados (se suma al giro de todo el montaje). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Giro = 0.f;
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

	/** Pantalla unica de las playlists viejas; al leer se convierte en una fila de Pantallas. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FDomePantalla Pantalla;

	/** Plantilla de pantallas del formato Plano169 y las filas (hasta 3). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FString Plantilla = TEXT("cine");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	TArray<FDomePantallaFila> Pantallas;

	/** Giro de todo el montaje, grados. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float GiroPantallas = 0.f;

	/** Recorrido (vueltas por segundo del cilindro y el tunel) y giro (grados por segundo) animados. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float VelRecorrido = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float VelGiro = 0.f;

	/** Fondo desenfocado detras de las pantallas (formato Plano169). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FDomeFondo Fondo;

	/** Volumen del audio del video (0 a 1 o mas). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	float Volumen = 1.f;

	/** true: el video se repite. false: al terminar pasa al siguiente cue (si bAutoAvanzar). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	bool Loop = true;

	/** El formato se adivina del video al abrirlo (cues agregados desde el menu). No se guarda. */
	UPROPERTY(Transient)
	bool bFormatoAuto = false;
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

	/** Reproductor de Media Framework a forzar. ElectraPlayer por defecto (decodifica H.264 y HEVC en la
	 *  GPU con D3D12 Video y NVDEC); si no abre un archivo se reintenta con WmfMedia. Vacio = automatico. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo")
	FName Reproductor = FName(TEXT("ElectraPlayer"));

	/** Cambia el reproductor: auto, electra (decodificador D3D12 en la GPU), protron (mp4 local sobre
	 *  Electra) o wmf (Windows Media Foundation, decodifica HEVC en CPU con DX12). Reabre el cue. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	void PonerReproductor(const FString& Nombre);

	/** Los cues cargados de la playlist (solo lectura; se editan en el JSON). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Domo")
	TArray<FDomeCue> Cues;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Domo")
	int32 CueActual = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Domo")
	bool bNegro = false;

	// --- Menu en pantalla ---------------------------------------------------------
	// Panel de Slate (DomeMenu.h) para operar sin TouchDesigner: fuente, videos,
	// imagen, luces, punto de vista, calidad y sala. F2 o M lo muestran y ocultan.

	/** El menu arranca visible fuera del editor (el ejecutable). En el editor arranca
	 *  oculto y se abre con F2. -DomoMenu=0|1 pisa las dos. */
	UPROPERTY(Config, EditAnywhere, Category = "Domo|Menu")
	bool bMenuAlArrancar = true;

	/** Ultimo aviso (se ve en el menu). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Domo|Menu")
	FString UltimoMensaje;

	UFUNCTION(BlueprintCallable, Category = "Domo|Menu")
	void MostrarMenu(bool bVer);

	UFUNCTION(BlueprintCallable, Category = "Domo|Menu")
	void AlternarMenu();

	/** Dibuja el menu en un PNG. Para verificar el aspecto sin ventana. */
	bool FotografiarMenu(const FString& Ruta, int32 Ancho, int32 Alto);

	/** Valor actual de un parametro del cue (los mismos nombres de SetParam). */
	UFUNCTION(BlueprintPure, Category = "Domo")
	float GetParam(FName Nombre) const;

	/** Repetir el cue actual. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	void SetLoop(bool bRepetir);

	/** Agrega videos a la lista (rutas completas) y salta al primero. El formato se
	 *  adivina del nombre del archivo o, si no, de las proporciones del video. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	int32 AgregarVideos(const TArray<FString>& Rutas);

	/** Agrega los videos de la carpeta de la playlist que aun no estan. Devuelve cuantos. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	int32 EscanearCarpeta();

	/** Escribe la playlist (con una copia .bak la primera vez). */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	bool GuardarPlaylist();

	/** Carpeta donde viven la playlist y los videos. */
	UFUNCTION(BlueprintPure, Category = "Domo")
	FString CarpetaVideos() const { return CarpetaPlaylist; }

	/** Mueve al jugador (cm, grados). Lo usan el menu y domo.Camara. */
	void IrAVista(const FVector& Ubicacion, const FRotator& Rotacion, const FString& Nombre);

	// --- Optimizar videos pesados ---------------------------------------------------------
	// Un video de 4096x4096 en HEVC (o 4K a 60 Mbps) no lo decodifica el reproductor de
	// Windows con la fluidez de un video de 2K: WMF decodifica en CPU con el motor en DX12
	// (medido: unos 3 nucleos de mas y cuadros perdidos). "Optimizar" hace con ffmpeg una
	// copia H.264 mas liviana (por defecto de 2048 de lado), con NVENC y, si falla, x264, y
	// la agrega a la lista con los mismos ajustes de imagen. Necesita ffmpeg (junto al
	// ejecutable, en la carpeta de los videos o en el PATH).

	/** Lado mayor de la copia optimizada, en pixeles. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Domo|Optimizar")
	int32 LadoOptimizado = 2048;

	/** Optimiza el video del cue actual en segundo plano. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	bool OptimizarVideoActual();

	bool EstaOptimizando() const { return bOptimizando; }
	void CancelarOptimizacion();

	// --- Pantallas 16:9 ---------------------------------------------------------------
	// Plantillas de pantallas (corona, 4 pantallas, 2 pantallas que ocupan el domo,
	// tunel, anillo, cilindro...) y edicion en vivo de cada fila. Son las de
	// TouchDesigner (video_dome). Se guardan en playlist.json con cada cue.

	static int32 NumeroDePlantillas();
	static FString IdDePlantilla(int32 Indice);
	static FString EtiquetaDePlantilla(int32 Indice);

	/** Indice de la plantilla del cue actual, o INDEX_NONE si esta editada a mano. */
	int32 IndiceDePlantillaActual() const;

	/** Pone las pantallas de la plantilla en el cue actual (y el formato en Plano169). */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	void AplicarPlantilla(const FString& Id);

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void AgregarPantalla();

	UFUNCTION(BlueprintCallable, Category = "Domo")
	void QuitarPantalla();

	/** Campo de la fila editada (Yaw, Elevacion, Ancho, Alto, Forma, Copias...) o del montaje
	 *  (GiroTodas, VelRecorrido, VelGiro). Editada = numero de fila desde 1. */
	float GetCampoPantalla(const FString& Campo) const;
	void SetCampoPantalla(const FString& Campo, float Valor);

	/** Fila que se edita en el menu (desde 0). */
	int32 PantallaEditada = 0;

	// --- Movimiento y teclas ------------------------------------------------------
	// Los ajustes de movimiento y las teclas viven en Controles y se guardan solos
	// en controles.json, junto a playlist.json. Ver DomeControles.h.

	FDomeControles Controles;

	bool MenuVisible() const;

	/** Empieza a esperar la proxima tecla para asignarla a la accion (ranura 0 o 1). */
	void EsperarTecla(EDomeAccion Accion, int32 Ranura);
	void CancelarEsperaDeTecla();
	bool EstaEsperandoTecla() const { return AccionEsperando >= 0; }
	int32 AccionEsperando = -1;
	int32 RanuraEsperando = 0;

	/** Empuja los ajustes de Controles al jugador y los guarda. */
	void AplicarMovimiento();
	void PonerModoMovimiento(EDomeModoMovimiento Modo);
	void RestablecerControles(bool bTeclas, bool bMovimiento);
	void GuardarControles();
	FString RutaControles() const;

	/** Vuelve al jugador al PlayerStart, con los pies en el piso. */
	void IrAlInicio();

	// --- Control por UDP ----------------------------------------------------------
	// TouchDesigner (UDP Out DAT), Resolume, QLab o un script mandan lineas de
	// texto a este puerto: cada linea es un comando de consola domo.* (domo.Cue 2,
	// domo.Luces 0, domo.Abrir C:/videos/a.mp4...). Solo se ejecutan los que
	// empiezan con "domo.". Escucha en 127.0.0.1 salvo que se pida la red.

	/** Puerto UDP de control. 0 = apagado. -DomoUdp=<puerto> lo pisa; -DomoUdpRed abre la red local. */
	UPROPERTY(Config, EditAnywhere, Category = "Domo|Control")
	int32 PuertoUdp = 7000;

	/** Escuchar en toda la red local (0.0.0.0) en vez de solo en este equipo. */
	UPROPERTY(Config, EditAnywhere, Category = "Domo|Control")
	bool bUdpEnRed = false;

	/** Una linea para el menu: en que puerto escucha (o que esta apagado). */
	FString DescribirUdp() const;

	/** Ejecuta una linea de control (la misma que llega por UDP). Devuelve false si no es un comando domo.*. */
	bool EjecutarLineaDeControl(const FString& Linea);

	/** Abre un video por ruta completa (lo agrega a la lista y lo pone). */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	bool AbrirVideoPorRuta(const FString& Ruta);

	// --- Luces de sala ------------------------------------------------------------
	// Las luces de la sala (franja y focos del muro, luces de pasillo, anillo de la
	// tarima) son los actores con la etiqueta EtiquetaLuces (las pone
	// 03_Unreal/realismo_sala.py). En una sala real solo estan encendidas cuando no
	// hay proyeccion: con LucesAutomaticas se apagan solas (con fundido) en cuanto
	// hay senal y vuelven al perderla. Las senales de salida no llevan la etiqueta:
	// nunca se apagan.

	/** Las luces siguen a la senal: apagadas con proyeccion, encendidas sin ella. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Luces")
	bool bLucesAutomaticas = true;

	/** Estado manual cuando LucesAutomaticas esta apagado (domo.Luces 0|1). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Luces")
	bool bLucesEncendidas = true;

	/** Segundos que tarda el fundido de las luces. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Luces")
	float SegundosFundidoLuces = 1.5f;

	/** Etiqueta (Tag) de los actores que son luces de sala. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Luces")
	FName EtiquetaLuces = FName(TEXT("domo_luz"));

	/** Etiqueta del actor que da el velo blanco-morado a la cupula cuando las luces estan
	 *  encendidas (lo crea 03_Unreal/realismo_sala.py). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Domo|Luces")
	FName EtiquetaResplandor = FName(TEXT("domo_resplandor"));

	/** Intensidad del velo de la cupula con las luces encendidas (0 lo apaga). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Domo|Luces")
	float IntensidadResplandor = 0.5f;

	/** Hay proyeccion: el Spout entrega cuadros, o el reproductor de Media esta en marcha. */
	UFUNCTION(BlueprintPure, Category = "Domo|Luces")
	bool HaySenal() const;

	/** Manual: enciende o apaga las luces y deja de seguir a la senal. */
	UFUNCTION(BlueprintCallable, Category = "Domo|Luces")
	void SetLuces(bool bEncender);

	/** Vuelve a seguir a la senal. */
	UFUNCTION(BlueprintCallable, Category = "Domo|Luces")
	void LucesAutomaticas(bool bActivar);

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

	/** Perfil de render segun la pantalla y la tarjeta: auto, vr, monitor, proyector o ligero.
	 *  El porcentaje de pantalla se calcula con la resolucion real de la ventana. "auto" elige por
	 *  visor conectado, fabricante, memoria de video y trazado de rayos. Se guarda en ajustes.json. */
	UFUNCTION(BlueprintCallable, Category = "Domo")
	void AplicarPerfil(const FString& Id);

	/** Descripcion corta del perfil y de la tarjeta para el menu y el log. */
	FString DescribirPerfil() const;

	/** Paredes de la sala: 0 negras, 1 con la madera original. Rugosidad del piso: multiplica la del
	 *  material (mas alto, menos reflejo). Se guardan en ajustes.json. */
	int32 ParedesModo = 0;
	float RugosidadPiso = 1.8f;
	FString PerfilActual = TEXT("auto");
	void AplicarSala();

	/** ajustes.json (junto a la playlist): perfil, paredes, piso, luces, velo, decodificador. */
	void GuardarAjustes();
	void MarcarAjustes();

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
	/** Si Electra no abre el archivo se reintenta por etapas: 0 Electra con todos sus decodificadores
	 *  de GPU (NVDEC y D3D12 Video), 1 Electra solo con el de Media Foundation (D3D12 Video apagado),
	 *  2 WmfMedia en CPU. EtapaAbierta es la del cue abierto; EtapaSiguiente la que pide el reintento. */
	bool bRespaldoPendiente = false;
	int32 EtapaAbierta = 0;
	int32 EtapaSiguiente = 0;
	int32 DimOptimizarX = 0;
	int32 DimOptimizarY = 0;
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
	void ActualizarLuces(float DeltaSeconds);

	/** 1 = luces encendidas, 0 = apagadas (con fundido). */
	float NivelLuces = 1.f;
	bool bLucesRecogidas = false;
	bool bLucesAplicadasUnaVez = false;
	double UltimaBusquedaLuces = -1000.0;

	/** Intensidad de cada luz cuando esta al 100 %. */
	TMap<TWeakObjectPtr<class ULightComponent>, float> IntensidadBase;
	TArray<TWeakObjectPtr<AActor>> ActoresLuz;
	void RecogerLuces();
	void ActualizarResplandor();
	TArray<TWeakObjectPtr<class UMaterialInstanceDynamic>> ResplandorMIDs;
	float UltimoResplandor = -1.f;
	void ConfigurarTeclado();
	TSharedPtr<FDomeMenu> Menu;
	FString CarpetaEnJson;
	FString NotaEnJson;
	bool bFormatoPendiente = false;
	bool bCopiaHecha = false;
	bool bMenuListo = false;
	float FpsMedio = 0.f;
	float CuadroMasLentoMs = 0.f;
	float FpsAcumTiempo = 0.f;
	float FpsAcumMax = 0.f;
	int32 FpsAcumCuadros = 0;
	bool bControlesSucios = false;
	double UltimoCambioControles = 0.0;
	bool bAjustesSucios = false;
	double UltimoCambioAjustes = 0.0;
	FString PerfilResuelto;
	FIntPoint UltimaResolucion = FIntPoint::ZeroValue;
	struct FMatSala
	{
		TWeakObjectPtr<class UMaterialInstanceDynamic> Mid;
		int32 Tipo = 0;                       // 0 muro, 1 listones, 2 piso
		FLinearColor TinteOriginal = FLinearColor::White;
		float RugOriginal = 1.f;
	};
	TArray<FMatSala> MatsSala;
	bool bSalaRecogida = false;
	void RecogerSala();
	void CargarAjustes();
	FString RutaAjustes() const;
	FString ElegirPerfilAuto() const;
	void AplicarResolucionInterna();
	void ProcesarTeclas();
	bool bOptimizando = false;
	int32 FaseOptimizar = 0;
	int32 CueOptimizado = INDEX_NONE;
	FProcHandle ProcOptimizar;
	FString EntradaOptimizar;
	FString SalidaOptimizar;
	FString ProgresoOptimizar;
	double DuracionOptimizar = 0.0;
	double UltimoAvisoOptimizar = 0.0;
	bool bPesoRevisado = false;
	FString BuscarFfmpeg() const;
	bool LanzarFfmpeg(int32 Fase);
	void ActualizarOptimizacion();
	void RevisarPeso();
	void EmpujarPantallas(const FDomeCue& C);
	void AnimarPantallas(float DeltaSeconds);
	float AcumRecorrido = 0.f;
	float AcumGiro = 0.f;
	void CapturarTecla(class APlayerController* PC);
	FSocket* SocketUdp = nullptr;
	FString UdpDescripcion;
	void AbrirUdp();
	void CerrarUdp();
	void LeerUdp();
	void ActualizarFormatoAuto();
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
	void TeclaMenu() { AlternarMenu(); }
	void TeclaCue(int32 Indice) { GoToCue(Indice); }
};
