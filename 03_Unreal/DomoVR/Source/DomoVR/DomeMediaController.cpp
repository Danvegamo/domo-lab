#include "DomeMediaController.h"

#include "SpoutDomeReceiver.h"
#include "DomeMenu.h"
#include "DomePawn.h"
#include "GameFramework/PlayerStart.h"

#include "Components/InputComponent.h"
#include "Components/LightComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Common/UdpSocketBuilder.h"
#include "Dom/JsonObject.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "RHI.h"
#include "RHIGlobals.h"
#include "IXRTrackingSystem.h"
#include "IHeadMountedDisplay.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FileMediaSource.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "MediaPlayer.h"
#include "MediaSoundComponent.h"
#include "MediaTexture.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogDomoMedia, Log, All);

// Nombres de los parametros de M_DomoMedia (los crea crear_media_domo.py; si
// se cambia uno aqui hay que cambiarlo alla).
namespace DomoParam
{
	static const FName Textura(TEXT("MediaTexture"));
	static const FName Formato(TEXT("Formato"));
	static const FName Brillo(TEXT("Brillo"));
	static const FName FovSala(TEXT("FovSala"));
	static const FName FovContenido(TEXT("FovContenido"));
	static const FName Yaw(TEXT("Yaw"));
	static const FName Pitch(TEXT("Pitch"));
	static const FName Roll(TEXT("Roll"));
	static const FName Horizonte(TEXT("Horizonte"));
	static const FName Curva(TEXT("Curva"));
	static const FName CentroX(TEXT("CentroX"));
	static const FName CentroY(TEXT("CentroY"));
	static const FName Escala(TEXT("Escala"));
	static const FName Rotar(TEXT("Rotar"));
	static const FName PantallaAzimut(TEXT("PantallaAzimut"));
	static const FName PantallaElevacion(TEXT("PantallaElevacion"));
	static const FName PantallaAncho(TEXT("PantallaAncho"));
	static const FName PantallaAlto(TEXT("PantallaAlto"));
	static const FName PantallaCurva(TEXT("PantallaCurva"));
	static const FName PantallaBorde(TEXT("PantallaBorde"));
	static const FName Volumen(TEXT("Volumen"));
}

namespace
{
	/** Campo flotante del cue que corresponde a un parametro, o nullptr. */
	float* CampoDelCue(FDomeCue& C, FName N)
	{
		if (N == DomoParam::Yaw) return &C.Yaw;
		if (N == DomoParam::Pitch) return &C.Pitch;
		if (N == DomoParam::Roll) return &C.Roll;
		if (N == DomoParam::Horizonte) return &C.Horizonte;
		if (N == DomoParam::Curva) return &C.Curva;
		if (N == DomoParam::FovContenido) return &C.FovContenido;
		if (N == DomoParam::CentroX) return &C.Mapping.CentroX;
		if (N == DomoParam::CentroY) return &C.Mapping.CentroY;
		if (N == DomoParam::Escala) return &C.Mapping.Escala;
		if (N == DomoParam::Rotar) return &C.Mapping.Rotar;
		if (N == DomoParam::PantallaAzimut) return &C.Pantalla.Azimut;
		if (N == DomoParam::PantallaElevacion) return &C.Pantalla.Elevacion;
		if (N == DomoParam::PantallaAncho) return &C.Pantalla.Ancho;
		if (N == DomoParam::PantallaAlto) return &C.Pantalla.Alto;
		if (N == DomoParam::PantallaBorde) return &C.Pantalla.Borde;
		if (N == DomoParam::Volumen) return &C.Volumen;
		return nullptr;
	}

	bool LeerNumero(const TSharedPtr<FJsonObject>& O, const TCHAR* Clave, float& Out)
	{
		double V = 0.0;
		if (O.IsValid() && O->TryGetNumberField(Clave, V))
		{
			Out = static_cast<float>(V);
			return true;
		}
		return false;
	}

	EDomeFormato FormatoDeTexto(FString T, bool& bOk)
	{
		bOk = true;
		T = T.ToLower().Replace(TEXT(" "), TEXT(""));
		if (T == TEXT("360") || T == TEXT("equirect") || T == TEXT("equirectangular")) return EDomeFormato::Equirect360;
		if (T == TEXT("domemaster") || T == TEXT("fisheye") || T == TEXT("180")) return EDomeFormato::Domemaster;
		if (T == TEXT("vr180")) return EDomeFormato::VR180;
		if (T == TEXT("vr180sbs") || T == TEXT("sbs")) return EDomeFormato::VR180SBS;
		if (T == TEXT("169") || T == TEXT("16:9") || T == TEXT("plano") || T == TEXT("pantalla")) return EDomeFormato::Plano169;
		bOk = false;
		return EDomeFormato::Equirect360;
	}

	const TCHAR* FormatoATexto(EDomeFormato F)
	{
		switch (F)
		{
		case EDomeFormato::Domemaster: return TEXT("domemaster");
		case EDomeFormato::VR180: return TEXT("vr180");
		case EDomeFormato::VR180SBS: return TEXT("vr180sbs");
		case EDomeFormato::Plano169: return TEXT("169");
		default: return TEXT("360");
		}
	}

	/** Formato por el nombre del archivo; false si el nombre no dice nada. */
	bool FormatoPorNombre(const FString& Nombre, EDomeFormato& Out)
	{
		const FString N = Nombre.ToLower();
		if (N.Contains(TEXT("vr180")))
		{
			Out = (N.Contains(TEXT("sbs")) || N.Contains(TEXT("lr"))) ? EDomeFormato::VR180SBS : EDomeFormato::VR180;
			return true;
		}
		if (N.Contains(TEXT("domemaster")) || N.Contains(TEXT("fisheye")) || N.Contains(TEXT("dome")))
		{
			Out = EDomeFormato::Domemaster;
			return true;
		}
		if (N.Contains(TEXT("360")) || N.Contains(TEXT("equirect")))
		{
			Out = EDomeFormato::Equirect360;
			return true;
		}
		if (N.Contains(TEXT("16x9")) || N.Contains(TEXT("169")) || N.Contains(TEXT("1080p")) || N.Contains(TEXT("1920x1080")))
		{
			Out = EDomeFormato::Plano169;
			return true;
		}
		return false;
	}

	bool EsVideo(const FString& Archivo)
	{
		const FString E = FPaths::GetExtension(Archivo).ToLower();
		return E == TEXT("mp4") || E == TEXT("mov") || E == TEXT("mkv") || E == TEXT("avi") || E == TEXT("m4v")
			|| E == TEXT("wmv") || E == TEXT("webm");
	}
}

// --- Pantallas 16:9 (plantillas, edicion en vivo, guardado) --------------------------

namespace
{
	const TCHAR* FormaATexto(int32 F)
	{
		switch (F)
		{
		case 1: return TEXT("curva");
		case 2: return TEXT("banda");
		case 3: return TEXT("tunel");
		case 4: return TEXT("cilindro");
		default: return TEXT("plana");
		}
	}

	int32 FormaDeTexto(const FString& T)
	{
		const FString L = T.ToLower();
		if (L == TEXT("curva")) return 1;
		if (L == TEXT("banda")) return 2;
		if (L == TEXT("tunel")) return 3;
		if (L == TEXT("cilindro")) return 4;
		return 0;
	}

	const TCHAR* EspejoATexto(int32 E)
	{
		switch (E)
		{
		case 1: return TEXT("horizontal");
		case 2: return TEXT("vertical");
		case 3: return TEXT("ambos");
		default: return TEXT("no");
		}
	}

	int32 EspejoDeTexto(const FString& T)
	{
		const FString L = T.ToLower();
		if (L == TEXT("horizontal")) return 1;
		if (L == TEXT("vertical")) return 2;
		if (L == TEXT("ambos")) return 3;
		return 0;
	}

	const TCHAR* BordesATexto(int32 B)
	{
		return B == 1 ? TEXT("costados") : (B == 2 ? TEXT("arriba_abajo") : TEXT("todos"));
	}

	int32 BordesDeTexto(const FString& T)
	{
		const FString L = T.ToLower();
		return L == TEXT("costados") ? 1 : (L == TEXT("arriba_abajo") ? 2 : 0);
	}

	FDomePantallaFila Fila(const TCHAR* Nombre, float Yaw, float Elev, float Ancho, float Alto, int32 Forma = 0)
	{
		FDomePantallaFila F;
		F.Nombre = Nombre;
		F.Yaw = Yaw;
		F.Elevacion = Elev;
		F.Ancho = Ancho;
		F.Alto = Alto;
		F.Forma = Forma;
		return F;
	}

	struct FPlantilla
	{
		const TCHAR* Id;
		const TCHAR* Etiqueta;
	};

	const FPlantilla Plantillas[] = {
		{ TEXT("cine"), TEXT("Una pantalla (cine)") },
		{ TEXT("grande"), TEXT("Una pantalla grande") },
		{ TEXT("bajo"), TEXT("Una pantalla baja") },
		{ TEXT("cenital"), TEXT("Una pantalla cenital") },
		{ TEXT("sala_2"), TEXT("2 pantallas que ocupan el domo") },
		{ TEXT("sala_4"), TEXT("4 pantallas (una frente a cada cuarto)") },
		{ TEXT("sala_6"), TEXT("6 pantallas") },
		{ TEXT("sala_4_espejo"), TEXT("4 pantallas espejadas") },
		{ TEXT("sala_6_mosaico"), TEXT("Mosaico de 6 (cada una un pedazo)") },
		{ TEXT("sala_corona"), TEXT("Corona (anillo de 6 + cenital)") },
		{ TEXT("sala_corona_panorama"), TEXT("Corona panoramica") },
		{ TEXT("tres"), TEXT("Tres pantallas") },
		{ TEXT("espejo"), TEXT("Dos pantallas espejadas") },
		{ TEXT("anillo"), TEXT("Anillo (banda alrededor)") },
		{ TEXT("anillo_doble"), TEXT("Anillo doble") },
		{ TEXT("tunel"), TEXT("Tunel") },
		{ TEXT("tunel_con_sala"), TEXT("Tunel con pantallas") },
		{ TEXT("cilindro"), TEXT("Cilindro (pared que sube)") },
		{ TEXT("cilindro_doble"), TEXT("Cilindro doble") },
		{ TEXT("cilindro_con_sala"), TEXT("Cilindro con pantallas") },
		{ TEXT("fragmentos"), TEXT("Fragmentos (un tercio cada una)") },
	};

	/** Las plantillas de video_dome/screens_module.py (TouchDesigner), a las mismas cifras.
	 *  GENERADO por 03_Unreal/generar_plantillas.py desde 00_TouchDesigner/video_dome/plantillas_ue.json: no editar a mano. */
	TArray<FDomePantallaFila> ArmarPlantilla(const FString& Id)
	{
		TArray<FDomePantallaFila> R;
		if (Id == TEXT("cine"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("cine"), 0.f, 40.f, 80.f, 45.f, 0);
				F.Borde = 0.06f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("grande"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("grande"), 0.f, 42.f, 120.f, 68.f, 1);
				F.Borde = 0.08f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("bajo"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("bajo"), 0.f, 30.f, 90.f, 51.f, 0);
				F.Borde = 0.06f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("cenital"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("cenital"), 0.f, 68.f, 100.f, 56.f, 1);
				F.Borde = 0.08f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("sala_2"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("dos_grandes"), 0.f, 44.f, 170.f, 59.f, 1);
				F.Solape = 12.f;
				F.Copias = 2;
				F.Bordes = 1;
				R.Add(F);
			}
		}
		else if (Id == TEXT("sala_4"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("cuatro"), 0.f, 42.f, 82.f, 46.f, 0);
				F.Solape = 8.f;
				F.Copias = 4;
				F.Bordes = 1;
				R.Add(F);
			}
		}
		else if (Id == TEXT("sala_6"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("seis"), 0.f, 40.f, 58.f, 33.f, 0);
				F.Solape = 8.f;
				F.Copias = 6;
				F.Bordes = 1;
				R.Add(F);
			}
		}
		else if (Id == TEXT("sala_4_espejo"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("cuatro_espejo"), 0.f, 42.f, 82.f, 46.f, 0);
				F.Solape = 8.f;
				F.Copias = 4;
				F.Bordes = 1;
				F.bEspejoAlterno = true;
				R.Add(F);
			}
		}
		else if (Id == TEXT("sala_6_mosaico"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("mosaico"), 0.f, 40.f, 58.f, 50.f, 1);
				F.CropX = 0.004f;
				F.CropY = 0.15f;
				F.CropW = 0.1787f;
				F.CropH = 0.7f;
				F.Solape = 8.f;
				F.Copias = 6;
				F.Corrimiento = 0.1667f;
				F.Bordes = 1;
				R.Add(F);
			}
		}
		else if (Id == TEXT("sala_corona"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("corona"), 0.f, 32.f, 66.f, 42.f, 0);
				F.Solape = 8.f;
				F.Copias = 6;
				F.bEspejoAlterno = true;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("cenital"), 0.f, 70.f, 96.f, 96.f, 1);
				F.Opacidad = 0.85f;
				F.Borde = 0.3f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("sala_corona_panorama"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("corona_pan"), 0.f, 32.f, 66.f, 42.f, 0);
				F.CropX = 0.004f;
				F.CropY = 0.1f;
				F.CropW = 0.1827f;
				F.CropH = 0.8f;
				F.Solape = 8.f;
				F.Copias = 6;
				F.Corrimiento = 0.1667f;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("cenital"), 0.f, 70.f, 96.f, 96.f, 1);
				F.Opacidad = 0.75f;
				F.Borde = 0.3f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("tres"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("izq"), -74.f, 40.f, 70.f, 30.f, 2);
				F.Espejo = 1;
				F.Borde = 0.05f;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("centro"), 0.f, 40.f, 70.f, 30.f, 2);
				F.Borde = 0.05f;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("der"), 74.f, 40.f, 70.f, 30.f, 2);
				F.Espejo = 1;
				F.Borde = 0.05f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("espejo"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("espejo"), 0.f, 40.f, 93.f, 40.f, 2);
				F.Borde = 0.05f;
				F.Solape = 6.f;
				F.Copias = 2;
				F.Arco = 93.f;
				F.bEspejoAlterno = true;
				R.Add(F);
			}
		}
		else if (Id == TEXT("anillo"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("anillo"), 0.f, 40.f, 360.f, 34.f, 2);
				F.Repeticion = 3.f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("anillo_doble"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("anillo_bajo"), 0.f, 28.f, 360.f, 24.f, 2);
				F.Repeticion = 4.f;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("anillo_alto"), 180.f, 58.f, 360.f, 22.f, 2);
				F.Espejo = 2;
				F.Opacidad = 0.85f;
				F.Repeticion = 2.f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("tunel"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("tunel"), 0.f, 90.f, 170.f, 170.f, 3);
				F.Repeticion = 4.f;
				R.Add(F);
			}
		}
		else if (Id == TEXT("tunel_con_sala"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("tunel"), 0.f, 90.f, 170.f, 170.f, 3);
				F.Opacidad = 0.6f;
				F.Repeticion = 5.f;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("sala"), 0.f, 38.f, 70.f, 39.f, 0);
				F.Borde = 0.06f;
				F.Copias = 4;
				R.Add(F);
			}
		}
		else if (Id == TEXT("cilindro"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("cilindro"), 0.f, 8.f, 360.f, 60.f, 4);
				F.Borde = 0.1f;
				F.Repeticion = 3.f;
				F.Recorrido = 1.f;
				F.Bordes = 2;
				R.Add(F);
			}
		}
		else if (Id == TEXT("cilindro_doble"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("pared"), 0.f, 6.f, 360.f, 42.f, 4);
				F.Borde = 0.08f;
				F.Repeticion = 3.f;
				F.Recorrido = 1.f;
				F.Bordes = 2;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("pared_alta"), 180.f, 50.f, 360.f, 30.f, 4);
				F.Espejo = 2;
				F.Opacidad = 0.8f;
				F.Borde = 0.12f;
				F.Repeticion = 2.f;
				F.Recorrido = -0.6f;
				F.Bordes = 2;
				R.Add(F);
			}
		}
		else if (Id == TEXT("cilindro_con_sala"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("cilindro"), 0.f, 8.f, 360.f, 70.f, 4);
				F.Opacidad = 0.55f;
				F.Borde = 0.1f;
				F.Repeticion = 3.f;
				F.Recorrido = 1.f;
				F.Bordes = 2;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("sala"), 0.f, 38.f, 70.f, 39.f, 0);
				F.Solape = 8.f;
				F.Copias = 4;
				F.Bordes = 1;
				R.Add(F);
			}
		}
		else if (Id == TEXT("fragmentos"))
		{
			{
				FDomePantallaFila F = Fila(TEXT("frag_izq"), -48.f, 42.f, 45.6f, 56.f, 2);
				F.CropW = 0.34f;
				F.Borde = 0.05f;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("frag_centro"), 0.f, 42.f, 45.6f, 56.f, 2);
				F.CropX = 0.33f;
				F.CropW = 0.34f;
				F.Borde = 0.05f;
				R.Add(F);
			}
			{
				FDomePantallaFila F = Fila(TEXT("frag_der"), 48.f, 42.f, 45.6f, 56.f, 2);
				F.CropX = 0.66f;
				F.CropW = 0.34f;
				F.Borde = 0.05f;
				R.Add(F);
			}
		}
		else { R.Add(Fila(TEXT("cine"), 0, 45, 70, 39)); }
		return R;
	}

	/** Una fila desde la vieja "pantalla" unica de la playlist. */
	FDomePantallaFila FilaDeLaPantallaVieja(const FDomePantalla& V)
	{
		FDomePantallaFila F = Fila(TEXT("pantalla"), V.Azimut, V.Elevacion, V.Ancho, V.Alto, V.bCurva ? 1 : 0);
		F.Borde = V.Borde;
		return F;
	}
}

// -----------------------------------------------------------------------------

ADomeMediaController::ADomeMediaController()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	// Despues del receptor de Spout (TG_PrePhysics): si los dos tocaran la
	// malla en el mismo frame, gana la fuente elegida.
	PrimaryActorTick.TickGroup = TG_PostPhysics;

	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Raiz"));

	// Audio del video. No espacial: la sala entera escucha lo mismo, como con
	// el sistema de sonido de un domo. Arranca apagado; BeginPlay lo enciende
	// solo en mundos de juego (el editor queda en silencio).
	MediaSound = CreateDefaultSubobject<UMediaSoundComponent>(TEXT("SonidoVideo"));
	MediaSound->SetupAttachment(RootComponent);
	MediaSound->bAutoActivate = false;
	MediaSound->bAllowSpatialization = false;
	MediaSound->bIsUISound = true;
	MediaSound->Channels = EMediaSoundChannels::Stereo;
}

bool ADomeMediaController::ShouldTickIfViewportsOnly() const
{
	// Igual que ASpoutDomeReceiver: tickea en el viewport del editor sin Play.
	return true;
}

bool ADomeMediaController::EsMundoDeJuego() const
{
	const UWorld* W = GetWorld();
	return W && W->IsGameWorld();
}

bool ADomeMediaController::EstaActivo() const
{
	const UWorld* W = GetWorld();
	if (!W)
	{
		return false;
	}
	if (W->IsGameWorld())
	{
		return true;
	}
	if (W->WorldType != EWorldType::Editor || !bReproducirEnEditor)
	{
		return false;
	}
	// Durante una sesion de PIE manda la copia del mundo de juego: la del
	// editor se queda quieta para no pelearse por MP_Domo (es un asset
	// compartido).
	if (GEngine)
	{
		for (const FWorldContext& Ctx : GEngine->GetWorldContexts())
		{
			if (Ctx.WorldType == EWorldType::PIE && Ctx.World())
			{
				return false;
			}
		}
	}
	return true;
}

void ADomeMediaController::BeginPlay()
{
	Super::BeginPlay();

	if (!EsMundoDeJuego())
	{
		return;
	}

	if (MediaSound && MediaPlayer)
	{
		MediaSound->SetMediaPlayer(MediaPlayer);
		MediaSound->SetEnableEnvelopeFollowing(true);
		MediaSound->Start();
	}

	// La fuente: en el editor (Play) la del actor, Spout; fuera del editor
	// (build, -game) FuenteFueraDelEditor, Media; -DomoFuente= pisa las dos.
	FString FuenteCmd;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoFuente="), FuenteCmd))
	{
		Fuente = FuenteCmd.Equals(TEXT("Spout"), ESearchCase::IgnoreCase) ? EDomeFuente::Spout : EDomeFuente::Media;
	}
	else if (!GIsEditor)
	{
		Fuente = FuenteFueraDelEditor;
	}
	UE_LOG(LogDomoMedia, Display, TEXT("Fuente al arrancar: %s"), Fuente == EDomeFuente::Media ? TEXT("Media") : TEXT("Spout"));

	FString Preset;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoPreset="), Preset))
	{
		AplicarPreset(Preset);
	}

	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("ElectraDecoders.bDoNotUseD3D12Video")))
	{
		V->Set(0, ECVF_SetByConsole);
	}
	Inicializar();
	CargarAjustes();
	ConfigurarTeclado();

	bool bVerMenu = GIsEditor ? false : bMenuAlArrancar;
	int32 CmdMenu = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoMenu="), CmdMenu))
	{
		bVerMenu = CmdMenu != 0;
	}
	if (GEngine && GEngine->GameViewport && !IsRunningDedicatedServer())
	{
		Menu = MakeShared<FDomeMenu>(this);
		if (Menu->Construir())
		{
			Menu->Mostrar(bVerMenu);
		}
		else
		{
			Menu.Reset();
		}
	}

	AbrirUdp();

	FString RutaGuion;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoGuion="), RutaGuion))
	{
		RutaGuion = FPaths::ConvertRelativePathToFull(RutaGuion);
		if (FFileHelper::LoadFileToStringArray(Guion, *RutaGuion))
		{
			UE_LOG(LogDomoMedia, Display, TEXT("Guion de prueba: %s (%d lineas)"), *RutaGuion, Guion.Num());
		}
		else
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("No se pudo leer el guion %s"), *RutaGuion);
		}
	}
}

namespace DomoPerfil
{
	/** Un perfil de render. PixelesM es la cantidad de pixeles internos (en millones) a la que apunta:
	 *  el porcentaje de pantalla sale de la resolucion real de la ventana, asi el mismo perfil sirve
	 *  en un monitor 1080p, en uno 4K o en un proyector. 0 = resolucion nativa (visor VR). */
	struct FDatos
	{
		const TCHAR* Id;
		const TCHAR* Nombre;
		double PixelesM;
		const TCHAR* HitLighting;
		const TCHAR* ReflDown;
		const TCHAR* ReflRug;
		const TCHAR* ProbeDown;
		const TCHAR* Octa;
		const TCHAR* TrazadoHw;
	};

	static const FDatos Tabla[] = {
		{ TEXT("vr"), TEXT("Visor VR"), 0.0, TEXT("0"), TEXT("2"), TEXT("0.4"), TEXT("16"), TEXT("8"), TEXT("1") },
		{ TEXT("monitor"), TEXT("Monitor"), 3.7, TEXT("0"), TEXT("1"), TEXT("0.5"), TEXT("12"), TEXT("8"), TEXT("1") },
		{ TEXT("proyector"), TEXT("Proyector o domo (alta)"), 8.3, TEXT("2"), TEXT("1"), TEXT("0.6"), TEXT("8"), TEXT("12"), TEXT("1") },
		{ TEXT("ligero"), TEXT("Ligero (tarjeta modesta)"), 1.6, TEXT("0"), TEXT("4"), TEXT("0.3"), TEXT("32"), TEXT("8"), TEXT("0") },
	};

	static const FDatos* Buscar(const FString& Id)
	{
		for (const FDatos& D : Tabla)
		{
			if (Id.Equals(D.Id, ESearchCase::IgnoreCase)) { return &D; }
		}
		return nullptr;
	}

	static FIntPoint TamanoVentana()
	{
		if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
		{
			const FIntPoint V = GEngine->GameViewport->Viewport->GetSizeXY();
			if (V.X > 0 && V.Y > 0) { return V; }
		}
		return FIntPoint(1920, 1080);
	}

	static int32 PorcentajeDePantalla(const FDatos& D)
	{
		if (D.PixelesM <= 0.0) { return 100; }
		const FIntPoint V = TamanoVentana();
		const double Pix = static_cast<double>(V.X) * static_cast<double>(V.Y);
		return FMath::Clamp(FMath::RoundToInt(static_cast<float>(100.0 * FMath::Sqrt(D.PixelesM * 1.0e6 / Pix))), 50, 200);
	}

	static void PonerCVar(const TCHAR* Nombre, const FString& Valor)
	{
		if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Nombre))
		{
			V->Set(*Valor, ECVF_SetByConsole);
		}
		else
		{
			UE_LOG(LogDomoMedia, Verbose, TEXT("Perfil: no existe %s en esta version del motor."), Nombre);
		}
	}

	static void Aplicar(const FDatos& D)
	{
		const int32 Sp = PorcentajeDePantalla(D);
		PonerCVar(TEXT("r.ScreenPercentage"), FString::FromInt(Sp));
		PonerCVar(TEXT("r.TSR.History.ScreenPercentage"), FString::FromInt(FMath::Max(Sp, 100)));
		PonerCVar(TEXT("r.Lumen.HardwareRayTracing.LightingMode"), D.HitLighting);
		PonerCVar(TEXT("r.Lumen.Reflections.DownsampleFactor"), D.ReflDown);
		PonerCVar(TEXT("r.Lumen.Reflections.MaxRoughnessToTrace"), D.ReflRug);
		PonerCVar(TEXT("r.Lumen.ScreenProbeGather.DownsampleFactor"), D.ProbeDown);
		PonerCVar(TEXT("r.Lumen.ScreenProbeGather.TracingOctahedronResolution"), D.Octa);
		PonerCVar(TEXT("r.Lumen.HardwareRayTracing"), D.TrazadoHw);
		PonerCVar(TEXT("r.SkyLight.RealTimeReflectionCapture.TimeSlice"), TEXT("0"));
	}
}

bool ADomeMediaController::AplicarPreset(const FString& Nombre)
{
	// Los presets viejos: "VR" es el perfil de visor y "Render" el de proyector o domo (alta).
	// Ver 04_Docs/02_Sala_Unreal.md, seccion "Presets VR y Render" y 06_Unreal_standalone.md, "Perfiles de render".
	FString Id = Nombre.ToLower();
	if (Id == TEXT("render")) { Id = TEXT("proyector"); }
	const DomoPerfil::FDatos* D = DomoPerfil::Buscar(Id);
	if (!D)
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("Preset desconocido '%s' (VR o Render; o un perfil: vr, monitor, proyector, ligero)."), *Nombre);
		return false;
	}
	DomoPerfil::Aplicar(*D);
	UE_LOG(LogDomoMedia, Display, TEXT("Preset de calidad: %s"), D->Nombre);
	return true;
}

void ADomeMediaController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	CerrarUdp();
	CancelarOptimizacion();
	Menu.Reset();
	bMenuListo = false;
	if (MediaPlayer)
	{
		MediaPlayer->OnEndReached.RemoveDynamic(this, &ADomeMediaController::AlTerminarVideo);
		MediaPlayer->OnMediaOpenFailed.RemoveDynamic(this, &ADomeMediaController::AlFallarApertura);
		if (EsMundoDeJuego())
		{
			MediaPlayer->Close();
		}
	}
	if (MediaSound && EsMundoDeJuego())
	{
		MediaSound->Stop();
	}
	Super::EndPlay(EndPlayReason);
}

void ADomeMediaController::Inicializar()
{
	if (bInicializado)
	{
		return;
	}
	bInicializado = true;

	if (!MediaPlayer || !MediaTexture || !MediaMaterial || !TargetMeshComponent)
	{
		UE_LOG(LogDomoMedia, Warning,
			TEXT("%s: faltan referencias (MediaPlayer, MediaTexture, MediaMaterial o TargetMeshComponent). ")
			TEXT("Correr 03_Unreal/crear_media_domo.ps1."), *GetName());
		return;
	}

	if (MediaTexture->GetMediaPlayer() != MediaPlayer)
	{
		MediaTexture->SetMediaPlayer(MediaPlayer);
	}

	DynamicMaterial = UMaterialInstanceDynamic::Create(MediaMaterial, this);
	// Transitoria: si el editor guarda el nivel con la cupula mostrando video,
	// la referencia se guarda nula y la malla vuelve a su material de siempre.
	DynamicMaterial->SetFlags(RF_Transient);

	MediaPlayer->OnEndReached.AddUniqueDynamic(this, &ADomeMediaController::AlTerminarVideo);
	MediaPlayer->OnMediaOpenFailed.AddUniqueDynamic(this, &ADomeMediaController::AlFallarApertura);

	CargarPlaylist(ResolverRutaPlaylist());
	if (Cues.Num() > 0)
	{
		AplicarParametros(Cues[FMath::Clamp(CueActual, 0, Cues.Num() - 1)]);
	}
	AplicarFuente();
	if (Controles.Cargar(RutaControles()))
	{
		UE_LOG(LogDomoMedia, Display, TEXT("Controles leidos de %s"), *RutaControles());
	}
	AplicarMovimiento();
}

FString ADomeMediaController::ResolverRutaPlaylist() const
{
	FString Ruta;
	if (FParse::Value(FCommandLine::Get(), TEXT("DomoPlaylist="), Ruta))
	{
		return FPaths::ConvertRelativePathToFull(Ruta);
	}
#if WITH_EDITOR
	if (GIsEditor && !RutaPlaylistEditor.IsEmpty())
	{
		return RutaPlaylistEditor;
	}
#endif
	if (FPaths::IsRelative(PlaylistPath))
	{
		return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / PlaylistPath);
	}
	return PlaylistPath;
}

bool ADomeMediaController::CargarPlaylist(const FString& Ruta)
{
	Cues.Reset();
	CarpetaPlaylist = FPaths::GetPath(Ruta);

	FString Texto;
	if (!FFileHelper::LoadFileToString(Texto, *Ruta))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("No existe la playlist %s. La cupula queda en negro."), *Ruta);
		Mensaje(FString::Printf(TEXT("Sin playlist: %s"), *Ruta), 8.f);
		return false;
	}

	TSharedPtr<FJsonObject> Raiz;
	const TSharedRef<TJsonReader<>> Lector = TJsonReaderFactory<>::Create(Texto);
	if (!FJsonSerializer::Deserialize(Lector, Raiz) || !Raiz.IsValid())
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("La playlist %s no es JSON valido: %s"), *Ruta, *Lector->GetErrorMessage());
		Mensaje(TEXT("Playlist con errores de JSON (ver log)"), 8.f);
		return false;
	}

	Raiz->TryGetStringField(TEXT("_nota"), NotaEnJson);
	FString Carpeta;
	CarpetaEnJson.Reset();
	if (Raiz->TryGetStringField(TEXT("carpeta"), Carpeta) && !Carpeta.IsEmpty())
	{
		CarpetaEnJson = Carpeta;
		CarpetaPlaylist = FPaths::IsRelative(Carpeta) ? FPaths::Combine(CarpetaPlaylist, Carpeta) : Carpeta;
	}

	const TArray<TSharedPtr<FJsonValue>>* Lista = nullptr;
	if (!Raiz->TryGetArrayField(TEXT("cues"), Lista) || !Lista)
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("La playlist %s no tiene la lista \"cues\"."), *Ruta);
		return false;
	}

	for (const TSharedPtr<FJsonValue>& Valor : *Lista)
	{
		const TSharedPtr<FJsonObject> O = Valor.IsValid() ? Valor->AsObject() : nullptr;
		if (!O.IsValid())
		{
			continue;
		}
		FDomeCue C;
		O->TryGetStringField(TEXT("archivo"), C.Archivo);
		if (C.Archivo.IsEmpty())
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("Cue %d sin \"archivo\"; se salta."), Cues.Num());
			continue;
		}
		if (!O->TryGetStringField(TEXT("nombre"), C.Nombre) || C.Nombre.IsEmpty())
		{
			C.Nombre = FPaths::GetBaseFilename(C.Archivo);
		}

		// Por tipo y no con TryGetNumberField: ese convierte el texto "360" en
		// el numero 360, que recortado a 0..4 daba el formato 4 (pasaba).
		const TSharedPtr<FJsonValue> CampoFormato = O->TryGetField(TEXT("formato"));
		if (CampoFormato.IsValid() && CampoFormato->Type == EJson::String)
		{
			bool bOk = false;
			C.Formato = FormatoDeTexto(CampoFormato->AsString(), bOk);
			if (!bOk)
			{
				UE_LOG(LogDomoMedia, Warning, TEXT("Cue '%s': formato '%s' desconocido; se usa 360."), *C.Nombre, *CampoFormato->AsString());
			}
		}
		else if (CampoFormato.IsValid() && CampoFormato->Type == EJson::Number)
		{
			C.Formato = static_cast<EDomeFormato>(FMath::Clamp(FMath::RoundToInt(CampoFormato->AsNumber()), 0, 4));
		}

		LeerNumero(O, TEXT("yaw"), C.Yaw);
		LeerNumero(O, TEXT("pitch"), C.Pitch);
		LeerNumero(O, TEXT("roll"), C.Roll);
		LeerNumero(O, TEXT("horizonte"), C.Horizonte);
		LeerNumero(O, TEXT("curva"), C.Curva);
		LeerNumero(O, TEXT("fovContenido"), C.FovContenido);
		LeerNumero(O, TEXT("volumen"), C.Volumen);
		O->TryGetBoolField(TEXT("loop"), C.Loop);

		const TSharedPtr<FJsonObject>* Map = nullptr;
		if (O->TryGetObjectField(TEXT("mapping"), Map) && Map)
		{
			LeerNumero(*Map, TEXT("centroX"), C.Mapping.CentroX);
			LeerNumero(*Map, TEXT("centroY"), C.Mapping.CentroY);
			LeerNumero(*Map, TEXT("escala"), C.Mapping.Escala);
			LeerNumero(*Map, TEXT("rotar"), C.Mapping.Rotar);
		}
		const TSharedPtr<FJsonObject>* Pan = nullptr;
		if (O->TryGetObjectField(TEXT("pantalla"), Pan) && Pan)
		{
			LeerNumero(*Pan, TEXT("azimut"), C.Pantalla.Azimut);
			LeerNumero(*Pan, TEXT("elevacion"), C.Pantalla.Elevacion);
			LeerNumero(*Pan, TEXT("ancho"), C.Pantalla.Ancho);
			LeerNumero(*Pan, TEXT("alto"), C.Pantalla.Alto);
			LeerNumero(*Pan, TEXT("borde"), C.Pantalla.Borde);
			(*Pan)->TryGetBoolField(TEXT("curva"), C.Pantalla.bCurva);
		}
		LeerNumero(O, TEXT("giroPantallas"), C.GiroPantallas);
		LeerNumero(O, TEXT("velRecorrido"), C.VelRecorrido);
		LeerNumero(O, TEXT("velGiro"), C.VelGiro);
		const TSharedPtr<FJsonObject>* Fon = nullptr;
		if (O->TryGetObjectField(TEXT("fondo"), Fon) && Fon)
		{
			double ModoF = C.Fondo.Modo;
			(*Fon)->TryGetNumberField(TEXT("modo"), ModoF);
			C.Fondo.Modo = FMath::Clamp(FMath::RoundToInt(static_cast<float>(ModoF)), 0, 2);
			LeerNumero(*Fon, TEXT("desenfoque"), C.Fondo.Desenfoque);
			LeerNumero(*Fon, TEXT("brillo"), C.Fondo.Brillo);
			LeerNumero(*Fon, TEXT("saturacion"), C.Fondo.Saturacion);
			LeerNumero(*Fon, TEXT("zoom"), C.Fondo.Zoom);
			LeerNumero(*Fon, TEXT("repeticiones"), C.Fondo.Repeticiones);
			LeerNumero(*Fon, TEXT("giro"), C.Fondo.Giro);
		}
		O->TryGetStringField(TEXT("plantilla"), C.Plantilla);
		const TArray<TSharedPtr<FJsonValue>>* Filas = nullptr;
		if (O->TryGetArrayField(TEXT("pantallas"), Filas) && Filas)
		{
			for (const TSharedPtr<FJsonValue>& FV : *Filas)
			{
				const TSharedPtr<FJsonObject> FO = FV.IsValid() ? FV->AsObject() : nullptr;
				if (!FO.IsValid() || C.Pantallas.Num() >= 3)
				{
					continue;
				}
				FDomePantallaFila F;
				FO->TryGetStringField(TEXT("nombre"), F.Nombre);
				FO->TryGetBoolField(TEXT("encendida"), F.bEncendida);
				FString Txt;
				if (FO->TryGetStringField(TEXT("forma"), Txt)) { F.Forma = FormaDeTexto(Txt); }
				if (FO->TryGetStringField(TEXT("espejo"), Txt)) { F.Espejo = EspejoDeTexto(Txt); }
				if (FO->TryGetStringField(TEXT("bordes"), Txt)) { F.Bordes = BordesDeTexto(Txt); }
				LeerNumero(FO, TEXT("yaw"), F.Yaw);
				LeerNumero(FO, TEXT("elevacion"), F.Elevacion);
				LeerNumero(FO, TEXT("roll"), F.Roll);
				LeerNumero(FO, TEXT("ancho"), F.Ancho);
				LeerNumero(FO, TEXT("alto"), F.Alto);
				LeerNumero(FO, TEXT("opacidad"), F.Opacidad);
				LeerNumero(FO, TEXT("cropX"), F.CropX);
				LeerNumero(FO, TEXT("cropY"), F.CropY);
				LeerNumero(FO, TEXT("cropW"), F.CropW);
				LeerNumero(FO, TEXT("cropH"), F.CropH);
				LeerNumero(FO, TEXT("borde"), F.Borde);
				LeerNumero(FO, TEXT("repeticion"), F.Repeticion);
				LeerNumero(FO, TEXT("solape"), F.Solape);
				double Nn = 0.0;
				if (FO->TryGetNumberField(TEXT("copias"), Nn)) { F.Copias = FMath::Clamp(FMath::RoundToInt(static_cast<float>(Nn)), 1, 12); }
				LeerNumero(FO, TEXT("arco"), F.Arco);
				FO->TryGetBoolField(TEXT("espejoAlterno"), F.bEspejoAlterno);
				LeerNumero(FO, TEXT("corrimiento"), F.Corrimiento);
				LeerNumero(FO, TEXT("recorrido"), F.Recorrido);
				LeerNumero(FO, TEXT("giro"), F.Giro);
				LeerNumero(FO, TEXT("brillo"), F.Brillo);
				C.Pantallas.Add(F);
			}
		}
		if (C.Pantallas.Num() == 0)
		{
			// playlist vieja (pantalla unica) o cue sin pantallas: una fila desde ahi
			C.Pantallas.Add(FilaDeLaPantallaVieja(C.Pantalla));
			C.Plantilla = TEXT("personalizado");
		}
		Cues.Add(C);
	}

	CueActual = Cues.Num() > 0 ? FMath::Clamp(CueActual, 0, Cues.Num() - 1) : 0;
	UE_LOG(LogDomoMedia, Display, TEXT("Playlist %s: %d cues."), *Ruta, Cues.Num());
	return Cues.Num() > 0;
}

void ADomeMediaController::AplicarParametros(const FDomeCue& C)
{
	if (!DynamicMaterial)
	{
		return;
	}
	UMaterialInstanceDynamic* M = DynamicMaterial;
	M->SetTextureParameterValue(DomoParam::Textura, MediaTexture);
	M->SetScalarParameterValue(DomoParam::Formato, static_cast<float>(static_cast<uint8>(C.Formato)));
	M->SetScalarParameterValue(DomoParam::FovSala, FovSala);
	M->SetScalarParameterValue(DomoParam::FovContenido, C.FovContenido);
	M->SetScalarParameterValue(DomoParam::Yaw, C.Yaw);
	M->SetScalarParameterValue(DomoParam::Pitch, C.Pitch);
	M->SetScalarParameterValue(DomoParam::Roll, C.Roll);
	M->SetScalarParameterValue(DomoParam::Horizonte, C.Horizonte);
	M->SetScalarParameterValue(DomoParam::Curva, C.Curva);
	M->SetScalarParameterValue(DomoParam::CentroX, C.Mapping.CentroX);
	M->SetScalarParameterValue(DomoParam::CentroY, C.Mapping.CentroY);
	M->SetScalarParameterValue(DomoParam::Escala, C.Mapping.Escala);
	M->SetScalarParameterValue(DomoParam::Rotar, C.Mapping.Rotar);
	EmpujarPantallas(C);
}

void ADomeMediaController::AbrirCue(int32 Indice)
{
	if (!Cues.IsValidIndex(Indice))
	{
		Mensaje(TEXT("La playlist no tiene cues"));
		return;
	}
	CueActual = Indice;
	const FDomeCue& C = Cues[Indice];
	AplicarParametros(C);
	bFormatoPendiente = C.bFormatoAuto;
	bPesoRevisado = false;
	AcumRecorrido = 0.f;
	AcumGiro = 0.f;

	if (Fuente != EDomeFuente::Media || !MediaPlayer)
	{
		bCueAbierto = false;
		return;
	}

	FString Ruta = C.Archivo;
	if (FPaths::IsRelative(Ruta))
	{
		Ruta = FPaths::Combine(CarpetaPlaylist, Ruta);
	}
	Ruta = FPaths::ConvertRelativePathToFull(Ruta);

	if (!FPaths::FileExists(Ruta))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("Cue %d '%s': no existe el archivo %s"), Indice + 1, *C.Nombre, *Ruta);
		Mensaje(FString::Printf(TEXT("Cue %d: falta %s"), Indice + 1, *FPaths::GetCleanFilename(Ruta)), 6.f);
		MediaPlayer->Close();
		bCueAbierto = false;
		return;
	}

	if (!FuenteArchivo)
	{
		FuenteArchivo = NewObject<UFileMediaSource>(this, NAME_None, RF_Transient);
	}
	FuenteArchivo->SetFilePath(Ruta);

	const FName Respaldo(TEXT("WmfMedia"));
	EtapaAbierta = bRespaldoPendiente ? EtapaSiguiente : 0;
	bRespaldoPendiente = false;
	EtapaSiguiente = 0;
	// D3D12 Video viene apagado de fabrica en el motor: se enciende (NVDEC le gana en NVIDIA) y solo se
	// apaga en la etapa 1, para probar el decodificador de Media Foundation de Electra.
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("ElectraDecoders.bDoNotUseD3D12Video")))
	{
		V->Set(EtapaAbierta == 1 ? 1 : 0, ECVF_SetByConsole);
	}
	MediaPlayer->SetDesiredPlayerName(EtapaAbierta >= 2 ? Respaldo : (EtapaAbierta == 1 && Reproductor.IsNone() ? FName(TEXT("ElectraPlayer")) : Reproductor));
	MediaPlayer->PlayOnOpen = true;
	MediaPlayer->SetLooping(C.Loop);
	bPendienteAvanzar = false;
	UltimoReintento = FPlatformTime::Seconds();
	const bool bOk = MediaPlayer->OpenSource(FuenteArchivo);
	bCueAbierto = bOk;

	UE_LOG(LogDomoMedia, Display, TEXT("Cue %d/%d '%s' (%s, formato %d, loop %d): %s"),
		Indice + 1, Cues.Num(), *C.Nombre, *Ruta, static_cast<int32>(C.Formato), C.Loop ? 1 : 0,
		bOk ? TEXT("abriendo") : TEXT("OpenSource devolvio false"));
	Mensaje(FString::Printf(TEXT("Cue %d/%d  %s"), Indice + 1, Cues.Num(), *C.Nombre));
}

void ADomeMediaController::AplicarFuente()
{
	if (Fuente == EDomeFuente::Media)
	{
		if (SpoutReceiver)
		{
			SpoutReceiver->SetActorTickEnabled(false);
		}
		AsegurarMaterialEnCupula();
		if (!bCueAbierto)
		{
			AbrirCue(CueActual);
		}
		else if (MediaPlayer && !bNegro)
		{
			MediaPlayer->Play();
		}
	}
	else
	{
		if (MediaPlayer)
		{
			MediaPlayer->Close();
		}
		bCueAbierto = false;
		if (SpoutReceiver)
		{
			SpoutReceiver->SetActorTickEnabled(true);
			SpoutReceiver->ReaplicarMaterial();
		}
	}
}

void ADomeMediaController::AsegurarMaterialEnCupula()
{
	if (TargetMeshComponent && DynamicMaterial && TargetMeshComponent->GetMaterial(TargetMaterialSlot) != DynamicMaterial)
	{
		TargetMeshComponent->SetMaterial(TargetMaterialSlot, DynamicMaterial);
	}
}

void ADomeMediaController::ActualizarNegroYVolumen(float DeltaSeconds)
{
	const float Objetivo = bNegro ? 1.f : 0.f;
	const float Paso = SegundosFundido > KINDA_SMALL_NUMBER ? DeltaSeconds / SegundosFundido : 1.f;
	AlfaNegro = FMath::Clamp(AlfaNegro + FMath::Sign(Objetivo - AlfaNegro) * FMath::Min(Paso, FMath::Abs(Objetivo - AlfaNegro)), 0.f, 1.f);

	if (DynamicMaterial)
	{
		DynamicMaterial->SetScalarParameterValue(DomoParam::Brillo, Brillo * (1.f - AlfaNegro));
	}
	if (MediaSound && EsMundoDeJuego())
	{
		const float Vol = Cues.IsValidIndex(CueActual) ? Cues[CueActual].Volumen : 1.f;
		MediaSound->SetVolumeMultiplier(FMath::Max(Vol * (1.f - AlfaNegro), 0.0001f));
	}
}

void ADomeMediaController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!EstaActivo())
	{
		return;
	}
	if (!bInicializado)
	{
		Inicializar();
	}
	if (!DynamicMaterial)
	{
		return;
	}

	if (Fuente == EDomeFuente::Media)
	{
		// El receptor de Spout arranca tickeando; mientras la fuente sea Media
		// se queda apagado para que no le devuelva a la cupula su material.
		if (SpoutReceiver && SpoutReceiver->IsActorTickEnabled())
		{
			SpoutReceiver->SetActorTickEnabled(false);
		}
		AsegurarMaterialEnCupula();

		if (bPendienteAvanzar)
		{
			bPendienteAvanzar = false;
			Next();
		}

		// Tras una sesion de PIE el reproductor queda cerrado (lo cierra la
		// copia de juego al terminar): la copia del editor lo vuelve a abrir.
		const double Ahora = FPlatformTime::Seconds();
		if (bCueAbierto && MediaPlayer && MediaPlayer->IsClosed() && Ahora - UltimoReintento > 2.0)
		{
			AbrirCue(CueActual);
		}
	}

	ActualizarNegroYVolumen(DeltaSeconds);
	ActualizarLuces(DeltaSeconds);

	if (EsMundoDeJuego())
	{
		ProcesarTeclas();
		if (bControlesSucios && FPlatformTime::Seconds() - UltimoCambioControles > 1.0)
		{
			GuardarControles();
		}
		if (Menu.IsValid() && !bMenuListo && GetWorld() && GetWorld()->GetFirstPlayerController())
		{
			// El jugador puede no existir aun en BeginPlay: se vuelve a aplicar el modo de entrada.
			bMenuListo = true;
			Menu->Mostrar(Menu->EstaVisible());
		}
		// Cuadros por segundo reales (ventana de 2 s) y el cuadro mas lento: domo.Estado los muestra.
		FpsAcumTiempo += DeltaSeconds;
		FpsAcumMax = FMath::Max(FpsAcumMax, DeltaSeconds);
		++FpsAcumCuadros;
		if (FpsAcumTiempo >= 2.f)
		{
			FpsMedio = FpsAcumCuadros / FpsAcumTiempo;
			CuadroMasLentoMs = FpsAcumMax * 1000.f;
			FpsAcumTiempo = 0.f;
			FpsAcumMax = 0.f;
			FpsAcumCuadros = 0;
		}
		if (bRespaldoPendiente && Fuente == EDomeFuente::Media && Cues.IsValidIndex(CueActual))
		{
			AbrirCue(CueActual);
		}
		if (!bSalaRecogida && GetWorld() && GetWorld()->GetTimeSeconds() > 1.0)
		{
			RecogerSala();
		}
		if (!PerfilResuelto.IsEmpty() && UltimaResolucion != DomoPerfil::TamanoVentana())
		{
			AplicarResolucionInterna();
		}
		if (bAjustesSucios && FPlatformTime::Seconds() - UltimoCambioAjustes > 1.0)
		{
			GuardarAjustes();
		}
		ActualizarFormatoAuto();
		RevisarPeso();
		ActualizarOptimizacion();
		AnimarPantallas(DeltaSeconds);
		LeerUdp();
		CorrerGuion(DeltaSeconds);
	}
}

// --- Luces de sala --------------------------------------------------------------

bool ADomeMediaController::HaySenal() const
{
	if (Fuente == EDomeFuente::Spout)
	{
		return SpoutReceiver && SpoutReceiver->HayCuadros();
	}
	return MediaPlayer && MediaPlayer->IsPlaying();
}

void ADomeMediaController::SetLuces(bool bEncender)
{
	bLucesAutomaticas = false;
	bLucesEncendidas = bEncender;
	MarcarAjustes();
}

void ADomeMediaController::LucesAutomaticas(bool bActivar)
{
	bLucesAutomaticas = bActivar;
	MarcarAjustes();
}

void ADomeMediaController::RecogerLuces()
{
	ActoresLuz.Reset();
	IntensidadBase.Reset();
	TArray<AActor*> Encontrados;
	UGameplayStatics::GetAllActorsWithTag(this, EtiquetaLuces, Encontrados);
	for (AActor* A : Encontrados)
	{
		ActoresLuz.Add(A);
		TArray<ULightComponent*> Luces;
		A->GetComponents<ULightComponent>(Luces);
		for (ULightComponent* L : Luces)
		{
			IntensidadBase.Add(L, L->Intensity);
		}
	}
	// El velo de la cupula (material aditivo): un MID por malla, con el parametro Nivel.
	ResplandorMIDs.Reset();
	TArray<AActor*> Velos;
	UGameplayStatics::GetAllActorsWithTag(this, EtiquetaResplandor, Velos);
	for (AActor* A : Velos)
	{
		TArray<UStaticMeshComponent*> Mallas;
		A->GetComponents<UStaticMeshComponent>(Mallas);
		for (UStaticMeshComponent* M : Mallas)
		{
			if (UMaterialInstanceDynamic* Mid = M->CreateDynamicMaterialInstance(0))
			{
				ResplandorMIDs.Add(Mid);
			}
		}
	}
	UltimoResplandor = -1.f;
	bLucesRecogidas = true;
	bLucesAplicadasUnaVez = false;
	UltimaBusquedaLuces = FPlatformTime::Seconds();
}

void ADomeMediaController::ActualizarResplandor()
{
	const float Nivel = NivelLuces * IntensidadResplandor;
	if (FMath::IsNearlyEqual(Nivel, UltimoResplandor, 0.0005f))
	{
		return;
	}
	UltimoResplandor = Nivel;
	for (const TWeakObjectPtr<UMaterialInstanceDynamic>& Ptr : ResplandorMIDs)
	{
		if (UMaterialInstanceDynamic* Mid = Ptr.Get())
		{
			Mid->SetScalarParameterValue(TEXT("Nivel"), Nivel);
		}
	}
}

void ADomeMediaController::ActualizarLuces(float DeltaSeconds)
{
	// Los actores de luz pueden crearse despues de BeginPlay (o en el editor): se
	// vuelve a buscar cada tanto mientras no haya ninguno.
	if (!bLucesRecogidas || (ActoresLuz.Num() == 0 && FPlatformTime::Seconds() - UltimaBusquedaLuces > 3.0))
	{
		RecogerLuces();
	}
	if (ActoresLuz.Num() == 0)
	{
		return;
	}

	const bool bEncendidas = bLucesAutomaticas ? !HaySenal() : bLucesEncendidas;
	const float Objetivo = bEncendidas ? 1.f : 0.f;
	const float Paso = SegundosFundidoLuces > KINDA_SMALL_NUMBER ? DeltaSeconds / SegundosFundidoLuces : 1.f;
	const float Anterior = NivelLuces;
	NivelLuces = FMath::Clamp(NivelLuces + FMath::Sign(Objetivo - NivelLuces) * FMath::Min(Paso, FMath::Abs(Objetivo - NivelLuces)), 0.f, 1.f);
	ActualizarResplandor();
	if (FMath::IsNearlyEqual(Anterior, NivelLuces) && (NivelLuces <= 0.f || NivelLuces >= 1.f) && bLucesAplicadasUnaVez)
	{
		return;
	}
	bLucesAplicadasUnaVez = true;

	for (const TWeakObjectPtr<AActor>& Ptr : ActoresLuz)
	{
		AActor* A = Ptr.Get();
		if (!A)
		{
			continue;
		}
		TArray<ULightComponent*> Luces;
		A->GetComponents<ULightComponent>(Luces);
		for (ULightComponent* L : Luces)
		{
			if (const float* Base = IntensidadBase.Find(L))
			{
				L->SetIntensity(*Base * NivelLuces);
				L->SetVisibility(NivelLuces > 0.005f);
			}
		}
		// Las mallas emisivas (franjas, LEDs) no tienen fundido: se ocultan al apagar.
		TArray<UStaticMeshComponent*> Mallas;
		A->GetComponents<UStaticMeshComponent>(Mallas);
		for (UStaticMeshComponent* M : Mallas)
		{
			M->SetVisibility(NivelLuces > 0.5f);
		}
	}
}

// --- Funciones publicas -------------------------------------------------------

void ADomeMediaController::Play()
{
	if (Fuente != EDomeFuente::Media)
	{
		SetFuente(EDomeFuente::Media);
		return;
	}
	if (!bCueAbierto)
	{
		AbrirCue(CueActual);
	}
	else if (MediaPlayer)
	{
		MediaPlayer->Play();
	}
}

void ADomeMediaController::Pause()
{
	if (MediaPlayer)
	{
		MediaPlayer->Pause();
	}
}

void ADomeMediaController::TogglePause()
{
	if (MediaPlayer && MediaPlayer->IsPlaying())
	{
		Pause();
		Mensaje(TEXT("Pausa"));
	}
	else
	{
		Play();
		Mensaje(TEXT("Play"));
	}
}

void ADomeMediaController::Next()
{
	if (Cues.Num() > 0)
	{
		GoToCue((CueActual + 1) % Cues.Num());
	}
}

void ADomeMediaController::Prev()
{
	if (Cues.Num() > 0)
	{
		GoToCue((CueActual - 1 + Cues.Num()) % Cues.Num());
	}
}

void ADomeMediaController::GoToCue(int32 Indice)
{
	if (!Cues.IsValidIndex(Indice))
	{
		Mensaje(FString::Printf(TEXT("No hay cue %d (la playlist tiene %d)"), Indice + 1, Cues.Num()));
		return;
	}
	if (!bInicializado)
	{
		CueActual = Indice;
		return;
	}
	AbrirCue(Indice);
}

void ADomeMediaController::Reiniciar()
{
	if (MediaPlayer && bCueAbierto)
	{
		MediaPlayer->Rewind();
		MediaPlayer->Play();
	}
}

void ADomeMediaController::SetParam(FName Nombre, float Valor)
{
	{
		const FString Txt = Nombre.ToString();
		if (Txt.StartsWith(TEXT("S_")))
		{
			SetCampoPantalla(Txt.Mid(2), Valor);
			return;
		}
		// nombres de la pantalla unica vieja: van a la primera fila
		static const TMap<FString, FString> Viejos = {
			{ TEXT("PantallaAzimut"), TEXT("Yaw") }, { TEXT("PantallaElevacion"), TEXT("Elevacion") },
			{ TEXT("PantallaAncho"), TEXT("Ancho") }, { TEXT("PantallaAlto"), TEXT("Alto") },
			{ TEXT("PantallaBorde"), TEXT("Borde") }, { TEXT("PantallaCurva"), TEXT("Forma") } };
		if (const FString* Nuevo = Viejos.Find(Txt))
		{
			const int32 Antes = PantallaEditada;
			PantallaEditada = 0;
			SetCampoPantalla(*Nuevo, *Nuevo == TEXT("Forma") ? (Valor > 0.5f ? 1.f : 0.f) : Valor);
			PantallaEditada = Antes;
			return;
		}
	}
	if (Nombre == TEXT("Resplandor")) { IntensidadResplandor = FMath::Max(Valor, 0.f); UltimoResplandor = -1.f; MarcarAjustes(); return; }
	if (Nombre == TEXT("LadoOptimizado")) { LadoOptimizado = FMath::Clamp(FMath::RoundToInt(Valor), 512, 4096); MarcarAjustes(); return; }
	if (Nombre == TEXT("Paredes")) { ParedesModo = Valor > 0.5f ? 1 : 0; AplicarSala(); MarcarAjustes(); return; }
	if (Nombre == TEXT("RugosidadPiso")) { RugosidadPiso = FMath::Clamp(Valor, 0.2f, 6.f); AplicarSala(); MarcarAjustes(); return; }
	if (Nombre == TEXT("VelCaminar")) { Controles.VelocidadCaminar = Valor; AplicarMovimiento(); return; }
	if (Nombre == TEXT("VelVuelo")) { Controles.VelocidadVuelo = Valor; AplicarMovimiento(); return; }
	if (Nombre == TEXT("MultCorrer")) { Controles.MultiplicadorCorrer = Valor; AplicarMovimiento(); return; }
	if (Nombre == TEXT("AlturaOjos")) { Controles.AlturaOjos = Valor; AplicarMovimiento(); return; }
	if (Nombre == TEXT("Sensibilidad")) { Controles.Sensibilidad = Valor; AplicarMovimiento(); return; }
	if (Nombre == TEXT("Gravedad")) { Controles.Gravedad = Valor; AplicarMovimiento(); return; }
	if (Nombre == DomoParam::Brillo)
	{
		Brillo = Valor;
		return;
	}
	if (Nombre == DomoParam::FovSala)
	{
		FovSala = Valor;
	}
	if (Cues.IsValidIndex(CueActual))
	{
		FDomeCue& C = Cues[CueActual];
		if (float* Campo = CampoDelCue(C, Nombre))
		{
			*Campo = Valor;
		}
		else if (Nombre == DomoParam::Formato)
		{
			C.Formato = static_cast<EDomeFormato>(FMath::Clamp(FMath::RoundToInt(Valor), 0, 4));
		}
		else if (Nombre == DomoParam::PantallaCurva)
		{
			C.Pantalla.bCurva = Valor > 0.5f;
		}
		else if (DynamicMaterial)
		{
			// Parametro del material que no es parte del cue (EspejoU, FovSala...).
			DynamicMaterial->SetScalarParameterValue(Nombre, Valor);
			return;
		}
		AplicarParametros(C);
	}
	else if (DynamicMaterial)
	{
		DynamicMaterial->SetScalarParameterValue(Nombre, Valor);
	}
}

void ADomeMediaController::Blackout(bool bActivar)
{
	bNegro = bActivar;
	Mensaje(bNegro ? TEXT("Negro") : TEXT("Imagen"));
}

void ADomeMediaController::ToggleBlackout()
{
	Blackout(!bNegro);
}

void ADomeMediaController::SetFuente(EDomeFuente NuevaFuente)
{
	Fuente = NuevaFuente;
	if (bInicializado)
	{
		AplicarFuente();
	}
	Mensaje(Fuente == EDomeFuente::Media ? TEXT("Fuente: Media") : TEXT("Fuente: Spout"));
}

void ADomeMediaController::ToggleFuente()
{
	SetFuente(Fuente == EDomeFuente::Media ? EDomeFuente::Spout : EDomeFuente::Media);
}

bool ADomeMediaController::RecargarPlaylist()
{
	const bool bOk = CargarPlaylist(ResolverRutaPlaylist());
	if (bOk && Fuente == EDomeFuente::Media)
	{
		AbrirCue(FMath::Clamp(CueActual, 0, Cues.Num() - 1));
	}
	return bOk;
}

FString ADomeMediaController::GetNombreCue(int32 Indice) const
{
	return Cues.IsValidIndex(Indice) ? Cues[Indice].Nombre : FString();
}

FString ADomeMediaController::DescribirEstado() const
{
	FString Rep = TEXT("-");
	float Tiempo = 0.f, Duracion = 0.f, Tasa = 0.f;
	int32 Audio = 0, VideoW = 0, VideoH = 0;
	if (MediaPlayer)
	{
		Rep = MediaPlayer->GetPlayerName().ToString();
		Tiempo = static_cast<float>(MediaPlayer->GetTime().GetTotalSeconds());
		Duracion = static_cast<float>(MediaPlayer->GetDuration().GetTotalSeconds());
		Tasa = MediaPlayer->GetRate();
		Audio = MediaPlayer->GetNumTracks(EMediaPlayerTrack::Audio);
	}
	if (MediaTexture)
	{
		VideoW = MediaTexture->GetWidth();
		VideoH = MediaTexture->GetHeight();
	}
	const float Envolvente = MediaSound ? MediaSound->GetEnvelopeValue() : 0.f;
	return FString::Printf(
		TEXT("fuente=%s cue=%d/%d '%s' reproductor=%s t=%.2f/%.2f tasa=%.2f textura=%dx%d pistas_audio=%d envolvente_audio=%.4f negro=%d fps=%.1f cuadro_mas_lento=%.0f ms"),
		Fuente == EDomeFuente::Media ? TEXT("Media") : TEXT("Spout"), CueActual + 1, Cues.Num(), *GetNombreCue(CueActual),
		*Rep, Tiempo, Duracion, Tasa, VideoW, VideoH, Audio, Envolvente, bNegro ? 1 : 0, FpsMedio, CuadroMasLentoMs);
}

// --- Eventos del reproductor --------------------------------------------------

void ADomeMediaController::AlTerminarVideo()
{
	if (!EstaActivo() || !Cues.IsValidIndex(CueActual))
	{
		return;
	}
	if (!Cues[CueActual].Loop && bAutoAvanzar)
	{
		// Se difiere al Tick: abrir otro archivo desde dentro del evento del
		// propio reproductor no es seguro.
		bPendienteAvanzar = true;
	}
}

void ADomeMediaController::PonerReproductor(const FString& Nombre)
{
	FName Nuevo = NAME_None;
	if (Nombre.Equals(TEXT("electra"), ESearchCase::IgnoreCase) || Nombre.Equals(TEXT("ElectraPlayer"), ESearchCase::IgnoreCase))
	{
		Nuevo = FName(TEXT("ElectraPlayer"));
	}
	else if (Nombre.Equals(TEXT("protron"), ESearchCase::IgnoreCase) || Nombre.Equals(TEXT("ElectraProtron"), ESearchCase::IgnoreCase))
	{
		Nuevo = FName(TEXT("ElectraProtron"));
	}
	else if (Nombre.Equals(TEXT("wmf"), ESearchCase::IgnoreCase) || Nombre.Equals(TEXT("WmfMedia"), ESearchCase::IgnoreCase))
	{
		Nuevo = FName(TEXT("WmfMedia"));
	}
	else if (!Nombre.Equals(TEXT("auto"), ESearchCase::IgnoreCase) && !Nombre.IsEmpty())
	{
		Nuevo = FName(*Nombre);
	}
	Reproductor = Nuevo;
	MarcarAjustes();
	UE_LOG(LogDomoMedia, Display, TEXT("Reproductor: %s"), Nuevo.IsNone() ? TEXT("automatico") : *Nuevo.ToString());
	if (Fuente == EDomeFuente::Media && Cues.IsValidIndex(CueActual))
	{
		AbrirCue(CueActual);
	}
}

void ADomeMediaController::AlFallarApertura(FString Url)
{
	if (!EstaActivo())
	{
		return;
	}
	const FName Respaldo(TEXT("WmfMedia"));
	if (EtapaAbierta < 2 && !Reproductor.IsNone() && Reproductor != Respaldo)
	{
		// Electra rechaza lo que su decodificador de GPU no acepta; se prueba el de Media Foundation de
		// Electra (etapa 1) y, por ultimo, WmfMedia, que decodifica en CPU (etapa 2).
		EtapaSiguiente = EtapaAbierta + 1;
		UE_LOG(LogDomoMedia, Warning, TEXT("%s no pudo abrir %s (etapa %d); se reintenta con %s."), *Reproductor.ToString(),
			Url.IsEmpty() && Cues.IsValidIndex(CueActual) ? *Cues[CueActual].Archivo : *Url, EtapaAbierta,
			EtapaSiguiente == 1 ? TEXT("el decodificador de Media Foundation de Electra") : TEXT("WmfMedia (decodifica en CPU)"));
		bRespaldoPendiente = true;
		return;
	}
	UE_LOG(LogDomoMedia, Warning, TEXT("No se pudo abrir %s con %s. Revisar el codec (H.264 o HEVC en .mp4; ver 04_Docs/06_Unreal_standalone.md)."),
		*Url, EtapaAbierta >= 2 ? *Respaldo.ToString() : *Reproductor.ToString());
	Mensaje(FString::Printf(TEXT("No se pudo abrir %s"), *FPaths::GetCleanFilename(Url)), 6.f);
	// No reintentar en bucle: queda cerrado hasta el proximo cambio de cue.
	bCueAbierto = false;
}

// --- Control por UDP ----------------------------------------------------------------

void ADomeMediaController::AbrirUdp()
{
	int32 Puerto = PuertoUdp;
	FParse::Value(FCommandLine::Get(), TEXT("DomoUdp="), Puerto);
	const bool bRed = bUdpEnRed || FParse::Param(FCommandLine::Get(), TEXT("DomoUdpRed"));
	if (Puerto <= 0)
	{
		UdpDescripcion = TEXT("Control por UDP apagado");
		return;
	}
	const FIPv4Address Direccion = bRed ? FIPv4Address::Any : FIPv4Address(127, 0, 0, 1);
	SocketUdp = FUdpSocketBuilder(TEXT("DomoControlUdp"))
		.AsNonBlocking()
		.AsReusable()
		.BoundToEndpoint(FIPv4Endpoint(Direccion, static_cast<uint16>(Puerto)))
		.WithReceiveBufferSize(65536)
		.Build();
	if (SocketUdp)
	{
		UdpDescripcion = FString::Printf(TEXT("Control por UDP en %s:%d (lineas domo.Cue 2, domo.Luces 0, domo.Abrir ruta...)"),
			bRed ? TEXT("toda la red") : TEXT("127.0.0.1"), Puerto);
	}
	else
	{
		UdpDescripcion = FString::Printf(TEXT("No se pudo abrir el puerto UDP %d (esta en uso?)"), Puerto);
	}
	UE_LOG(LogDomoMedia, Display, TEXT("%s"), *UdpDescripcion);
}

void ADomeMediaController::CerrarUdp()
{
	if (SocketUdp)
	{
		SocketUdp->Close();
		if (ISocketSubsystem* Subsistema = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM))
		{
			Subsistema->DestroySocket(SocketUdp);
		}
		SocketUdp = nullptr;
	}
}

FString ADomeMediaController::DescribirUdp() const
{
	return UdpDescripcion;
}

void ADomeMediaController::LeerUdp()
{
	if (!SocketUdp)
	{
		return;
	}
	uint32 Tamano = 0;
	int32 Limite = 32;	// paquetes por cuadro
	while (Limite-- > 0 && SocketUdp->HasPendingData(Tamano))
	{
		TArray<uint8> Bytes;
		Bytes.SetNumZeroed(static_cast<int32>(FMath::Min<uint32>(Tamano, 65507u)) + 1);
		int32 Leidos = 0;
		if (!SocketUdp->Recv(Bytes.GetData(), Bytes.Num() - 1, Leidos) || Leidos <= 0)
		{
			break;
		}
		Bytes[Leidos] = 0;
		const FString Texto = FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(Bytes.GetData())));
		TArray<FString> Lineas;
		Texto.ParseIntoArrayLines(Lineas);
		for (const FString& Linea : Lineas)
		{
			EjecutarLineaDeControl(Linea);
		}
	}
}

bool ADomeMediaController::EjecutarLineaDeControl(const FString& LineaCruda)
{
	const FString Linea = LineaCruda.TrimStartAndEnd();
	if (!Linea.StartsWith(TEXT("domo."), ESearchCase::IgnoreCase))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("Control: se ignora '%s' (solo comandos domo.*)"), *Linea);
		return false;
	}
	UE_LOG(LogDomoMedia, Display, TEXT("Control> %s"), *Linea);
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (PC)
	{
		PC->ConsoleCommand(Linea, true);
	}
	else if (GEngine)
	{
		GEngine->Exec(GetWorld(), *Linea);
	}
	return true;
}

bool ADomeMediaController::AbrirVideoPorRuta(const FString& Ruta)
{
	return AgregarVideos({ Ruta }) > 0 || Cues.Num() > 0;
}

// --- Pantallas 16:9: plantillas y edicion en vivo -----------------------------------

int32 ADomeMediaController::NumeroDePlantillas()
{
	return UE_ARRAY_COUNT(Plantillas);
}

FString ADomeMediaController::IdDePlantilla(int32 Indice)
{
	return Indice >= 0 && Indice < UE_ARRAY_COUNT(Plantillas) ? FString(Plantillas[Indice].Id) : FString();
}

FString ADomeMediaController::EtiquetaDePlantilla(int32 Indice)
{
	return Indice >= 0 && Indice < UE_ARRAY_COUNT(Plantillas) ? FString(Plantillas[Indice].Etiqueta) : FString();
}

int32 ADomeMediaController::IndiceDePlantillaActual() const
{
	if (!Cues.IsValidIndex(CueActual))
	{
		return 0;
	}
	for (int32 i = 0; i < UE_ARRAY_COUNT(Plantillas); ++i)
	{
		if (Cues[CueActual].Plantilla == Plantillas[i].Id)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

void ADomeMediaController::AplicarPlantilla(const FString& Id)
{
	if (!Cues.IsValidIndex(CueActual))
	{
		return;
	}
	FDomeCue& C = Cues[CueActual];
	C.Plantilla = Id;
	C.Pantallas = ArmarPlantilla(Id);
	C.VelRecorrido = 0.f;
	C.VelGiro = 0.f;
	for (const FDomePantallaFila& F : C.Pantallas)
	{
		if (!FMath::IsNearlyZero(F.Recorrido)) { C.VelRecorrido = 0.05f; }
	}
	PantallaEditada = 0;
	if (C.Formato != EDomeFormato::Plano169)
	{
		C.Formato = EDomeFormato::Plano169;
		C.bFormatoAuto = false;
	}
	AplicarParametros(C);
	Mensaje(FString::Printf(TEXT("Pantallas: %s"), *EtiquetaDePlantilla(IndiceDePlantillaActual())));
}

void ADomeMediaController::AgregarPantalla()
{
	if (!Cues.IsValidIndex(CueActual) || Cues[CueActual].Pantallas.Num() >= 3)
	{
		Mensaje(TEXT("Hay lugar para 3 pantallas (filas) como maximo"));
		return;
	}
	FDomeCue& C = Cues[CueActual];
	C.Pantallas.Add(Fila(TEXT("pantalla"), 0, 45, 70, 39));
	C.Plantilla = TEXT("personalizado");
	PantallaEditada = C.Pantallas.Num() - 1;
	AplicarParametros(C);
}

void ADomeMediaController::QuitarPantalla()
{
	if (!Cues.IsValidIndex(CueActual) || Cues[CueActual].Pantallas.Num() <= 1)
	{
		Mensaje(TEXT("Tiene que quedar al menos una pantalla"));
		return;
	}
	FDomeCue& C = Cues[CueActual];
	C.Pantallas.RemoveAt(FMath::Clamp(PantallaEditada, 0, C.Pantallas.Num() - 1));
	C.Plantilla = TEXT("personalizado");
	PantallaEditada = FMath::Clamp(PantallaEditada, 0, C.Pantallas.Num() - 1);
	AplicarParametros(C);
}

namespace
{
	/** Campo flotante de una fila por nombre; los enteros y booleanos van como float. */
	float* CampoDeFila(FDomePantallaFila& F, const FString& N)
	{
		if (N == TEXT("Yaw")) return &F.Yaw;
		if (N == TEXT("Elevacion")) return &F.Elevacion;
		if (N == TEXT("Roll")) return &F.Roll;
		if (N == TEXT("Ancho")) return &F.Ancho;
		if (N == TEXT("Alto")) return &F.Alto;
		if (N == TEXT("Opacidad")) return &F.Opacidad;
		if (N == TEXT("CropX")) return &F.CropX;
		if (N == TEXT("CropY")) return &F.CropY;
		if (N == TEXT("CropW")) return &F.CropW;
		if (N == TEXT("CropH")) return &F.CropH;
		if (N == TEXT("Borde")) return &F.Borde;
		if (N == TEXT("Repeticion")) return &F.Repeticion;
		if (N == TEXT("Solape")) return &F.Solape;
		if (N == TEXT("Arco")) return &F.Arco;
		if (N == TEXT("Corrimiento")) return &F.Corrimiento;
		if (N == TEXT("Recorrido")) return &F.Recorrido;
		if (N == TEXT("Giro")) return &F.Giro;
		if (N == TEXT("Brillo")) return &F.Brillo;
		return nullptr;
	}
}

float ADomeMediaController::GetCampoPantalla(const FString& Campo) const
{
	if (!Cues.IsValidIndex(CueActual))
	{
		return 0.f;
	}
	const FDomeCue& C = Cues[CueActual];
	if (Campo == TEXT("Editada")) return static_cast<float>(PantallaEditada + 1);
	if (Campo == TEXT("Fondo_Modo")) return static_cast<float>(C.Fondo.Modo);
	if (Campo == TEXT("Fondo_Desenfoque")) return C.Fondo.Desenfoque;
	if (Campo == TEXT("Fondo_Brillo")) return C.Fondo.Brillo;
	if (Campo == TEXT("Fondo_Saturacion")) return C.Fondo.Saturacion;
	if (Campo == TEXT("Fondo_Zoom")) return C.Fondo.Zoom;
	if (Campo == TEXT("Fondo_Repeticiones")) return C.Fondo.Repeticiones;
	if (Campo == TEXT("Fondo_Giro")) return C.Fondo.Giro;
	if (Campo == TEXT("GiroTodas")) return C.GiroPantallas;
	if (Campo == TEXT("VelRecorrido")) return C.VelRecorrido;
	if (Campo == TEXT("VelGiro")) return C.VelGiro;
	if (!C.Pantallas.IsValidIndex(PantallaEditada)) return 0.f;
	FDomePantallaFila& F = const_cast<FDomePantallaFila&>(C.Pantallas[PantallaEditada]);
	if (Campo == TEXT("Encendida")) return F.bEncendida ? 1.f : 0.f;
	if (Campo == TEXT("Forma")) return static_cast<float>(F.Forma);
	if (Campo == TEXT("Espejo")) return static_cast<float>(F.Espejo);
	if (Campo == TEXT("Bordes")) return static_cast<float>(F.Bordes);
	if (Campo == TEXT("Copias")) return static_cast<float>(F.Copias);
	if (Campo == TEXT("EspejoAlterno")) return F.bEspejoAlterno ? 1.f : 0.f;
	if (const float* P = CampoDeFila(F, Campo)) return *P;
	return 0.f;
}

void ADomeMediaController::SetCampoPantalla(const FString& Campo, float Valor)
{
	if (!Cues.IsValidIndex(CueActual))
	{
		return;
	}
	FDomeCue& C = Cues[CueActual];
	if (Campo == TEXT("Editada"))
	{
		PantallaEditada = FMath::Clamp(FMath::RoundToInt(Valor) - 1, 0, FMath::Max(C.Pantallas.Num() - 1, 0));
		return;
	}
	if (Campo.StartsWith(TEXT("Fondo_")))
	{
		if (Campo == TEXT("Fondo_Modo")) C.Fondo.Modo = FMath::Clamp(FMath::RoundToInt(Valor), 0, 2);
		else if (Campo == TEXT("Fondo_Desenfoque")) C.Fondo.Desenfoque = FMath::Clamp(Valor, 0.f, 200.f);
		else if (Campo == TEXT("Fondo_Brillo")) C.Fondo.Brillo = FMath::Clamp(Valor, 0.f, 2.f);
		else if (Campo == TEXT("Fondo_Saturacion")) C.Fondo.Saturacion = FMath::Clamp(Valor, 0.f, 2.f);
		else if (Campo == TEXT("Fondo_Zoom")) C.Fondo.Zoom = FMath::Clamp(Valor, 1.f, 4.f);
		else if (Campo == TEXT("Fondo_Repeticiones")) C.Fondo.Repeticiones = FMath::Clamp(Valor, 1.f, 8.f);
		else if (Campo == TEXT("Fondo_Giro")) C.Fondo.Giro = Valor;
		AplicarParametros(C);
		return;
	}
	if (Campo == TEXT("GiroTodas")) { C.GiroPantallas = Valor; AplicarParametros(C); return; }
	if (Campo == TEXT("VelRecorrido")) { C.VelRecorrido = Valor; return; }
	if (Campo == TEXT("VelGiro")) { C.VelGiro = Valor; return; }
	if (!C.Pantallas.IsValidIndex(PantallaEditada)) return;
	FDomePantallaFila& F = C.Pantallas[PantallaEditada];
	if (Campo == TEXT("Encendida")) F.bEncendida = Valor > 0.5f;
	else if (Campo == TEXT("Forma")) F.Forma = FMath::Clamp(FMath::RoundToInt(Valor), 0, 4);
	else if (Campo == TEXT("Espejo")) F.Espejo = FMath::Clamp(FMath::RoundToInt(Valor), 0, 3);
	else if (Campo == TEXT("Bordes")) F.Bordes = FMath::Clamp(FMath::RoundToInt(Valor), 0, 2);
	else if (Campo == TEXT("Copias")) F.Copias = FMath::Clamp(FMath::RoundToInt(Valor), 1, 12);
	else if (Campo == TEXT("EspejoAlterno")) F.bEspejoAlterno = Valor > 0.5f;
	else if (float* P = CampoDeFila(F, Campo)) *P = Valor;
	else return;
	if (C.Plantilla != TEXT("personalizado") && !C.Plantilla.EndsWith(TEXT("*")))
	{
		C.Plantilla += TEXT("*");
	}
	AplicarParametros(C);
}

void ADomeMediaController::EmpujarPantallas(const FDomeCue& C)
{
	if (!DynamicMaterial)
	{
		return;
	}
	UMaterialInstanceDynamic* M = DynamicMaterial;
	const int32 N = FMath::Min(C.Pantallas.Num(), 3);
	M->SetVectorParameterValue(TEXT("PView"), FLinearColor(static_cast<float>(N), C.GiroPantallas, AcumRecorrido, AcumGiro));
	M->SetVectorParameterValue(TEXT("PBg0"), FLinearColor(static_cast<float>(C.Fondo.Modo), C.Fondo.Desenfoque, C.Fondo.Brillo, C.Fondo.Saturacion));
	M->SetVectorParameterValue(TEXT("PBg1"), FLinearColor(C.Fondo.Zoom, C.Fondo.Repeticiones, C.Fondo.Giro + C.GiroPantallas, 0.f));
	for (int32 i = 0; i < 3; ++i)
	{
		const FString S = FString::FromInt(i);
		if (i >= N)
		{
			for (const TCHAR* K : { TEXT("PPos"), TEXT("PSize"), TEXT("PCrop"), TEXT("POpt"), TEXT("PRep"), TEXT("PAnm") })
			{
				M->SetVectorParameterValue(FName(*(FString(K) + S)), FLinearColor(0, 0, 1, 0));
			}
			continue;
		}
		const FDomePantallaFila& F = C.Pantallas[i];
		M->SetVectorParameterValue(FName(*(FString(TEXT("PPos")) + S)), FLinearColor(F.Yaw, F.Elevacion, F.Roll, static_cast<float>(F.Forma)));
		M->SetVectorParameterValue(FName(*(FString(TEXT("PSize")) + S)), FLinearColor(F.Ancho, F.Alto, static_cast<float>(F.Espejo), F.Opacidad));
		M->SetVectorParameterValue(FName(*(FString(TEXT("PCrop")) + S)), FLinearColor(F.CropX, F.CropY, F.CropW, F.CropH));
		M->SetVectorParameterValue(FName(*(FString(TEXT("POpt")) + S)), FLinearColor(F.bEncendida ? 1.f : 0.f, F.Borde, F.Repeticion, F.Solape));
		M->SetVectorParameterValue(FName(*(FString(TEXT("PRep")) + S)), FLinearColor(static_cast<float>(F.Copias), F.Arco, F.bEspejoAlterno ? 1.f : 0.f, F.Corrimiento));
		M->SetVectorParameterValue(FName(*(FString(TEXT("PAnm")) + S)), FLinearColor(F.Recorrido, F.Giro, static_cast<float>(F.Bordes), F.Brillo));
	}
}

void ADomeMediaController::AnimarPantallas(float DeltaSeconds)
{
	if (!Cues.IsValidIndex(CueActual) || Cues[CueActual].Formato != EDomeFormato::Plano169)
	{
		return;
	}
	const FDomeCue& C = Cues[CueActual];
	if (FMath::IsNearlyZero(C.VelRecorrido) && FMath::IsNearlyZero(C.VelGiro))
	{
		return;
	}
	AcumRecorrido = FMath::Fmod(AcumRecorrido + C.VelRecorrido * DeltaSeconds, 1000.f);
	AcumGiro = FMath::Fmod(AcumGiro + C.VelGiro * DeltaSeconds, 360000.f);
	EmpujarPantallas(C);
}

// --- Optimizar videos pesados --------------------------------------------------------------

void ADomeMediaController::RevisarPeso()
{
	if (bPesoRevisado || !MediaPlayer || !Cues.IsValidIndex(CueActual) || !MediaPlayer->IsReady())
	{
		return;
	}
	const FIntPoint D = MediaPlayer->GetVideoTrackDimensions(INDEX_NONE, INDEX_NONE);
	if (D.X <= 0 || D.Y <= 0)
	{
		return;
	}
	bPesoRevisado = true;
	// Solo WmfMedia decodifica en CPU; Electra usa la GPU (D3D12 Video o NVDEC) y no necesita la copia liviana.
	if (FMath::Max(D.X, D.Y) >= 3500 && MediaPlayer->GetPlayerName() == FName(TEXT("WmfMedia")))
	{
		Mensaje(FString::Printf(TEXT("Video pesado (%dx%d) decodificado en CPU: puede trabarse. Menu > Fuente y video > Optimizar video hace una copia liviana."), D.X, D.Y), 12.f);
	}
}

FString ADomeMediaController::BuscarFfmpeg() const
{
	TArray<FString> Candidatos;
	Candidatos.Add(FPaths::Combine(FPlatformProcess::BaseDir(), TEXT("ffmpeg.exe")));
	Candidatos.Add(FPaths::Combine(FPaths::ConvertRelativePathToFull(CarpetaPlaylist), TEXT("ffmpeg.exe")));
	Candidatos.Add(FPaths::Combine(FPaths::ConvertRelativePathToFull(CarpetaPlaylist), TEXT("ffmpeg"), TEXT("ffmpeg.exe")));
	FString Ruta = FPlatformMisc::GetEnvironmentVariable(TEXT("PATH"));
	TArray<FString> Carpetas;
	Ruta.ParseIntoArray(Carpetas, TEXT(";"), true);
	for (const FString& C : Carpetas)
	{
		Candidatos.Add(FPaths::Combine(C, TEXT("ffmpeg.exe")));
	}
	for (const FString& C : Candidatos)
	{
		if (FPaths::FileExists(C))
		{
			return C;
		}
	}
	return FString();
}

bool ADomeMediaController::LanzarFfmpeg(int32 Fase)
{
	const FString Ffmpeg = BuscarFfmpeg();
	if (Ffmpeg.IsEmpty())
	{
		Mensaje(TEXT("No encuentro ffmpeg. Ponlo junto al ejecutable, en la carpeta de los videos o en el PATH."), 10.f);
		return false;
	}
	IFileManager::Get().Delete(*SalidaOptimizar, false, true, true);
	IFileManager::Get().Delete(*ProgresoOptimizar, false, true, true);
	const int32 L = FMath::Clamp(LadoOptimizado, 512, 4096);
	// Tamano de salida: el del video encajado en L x L, con ancho y alto pares (vpp_qsv no tiene
	// force_original_aspect_ratio, asi que el filtro de Intel recibe el tamano ya calculado).
	int32 W = L, H = L;
	if (DimOptimizarX > 0 && DimOptimizarY > 0)
	{
		const float Escala = FMath::Min(1.f, static_cast<float>(L) / static_cast<float>(FMath::Max(DimOptimizarX, DimOptimizarY)));
		W = FMath::Max(2, (FMath::RoundToInt(DimOptimizarX * Escala) / 2) * 2);
		H = FMath::Max(2, (FMath::RoundToInt(DimOptimizarY * Escala) / 2) * 2);
	}
	const FString FiltroCpu = FString::Printf(
		TEXT("scale='min(%d,iw)':'min(%d,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"), L, L);

	// Fase 0: decodifica, escala y codifica con la GPU. Fase 1: decodifica en CPU y codifica con la GPU.
	// Fase 2: todo en CPU (x264). El codificador de GPU depende del fabricante (sus ejemplos y limites,
	// en 04_Docs/07_GPUs_AMD_e_Intel.md, seccion 4): NVIDIA NVENC, AMD AMF, Intel Quick Sync.
	FString Entrada, Filtro, Video;
	if (Fase == 2 || (!IsRHIDeviceNVIDIA() && !IsRHIDeviceAMD() && !IsRHIDeviceIntel()))
	{
		Fase = 2;
		Filtro = FiltroCpu;
		Video = TEXT("-c:v libx264 -preset veryfast -crf 20 -profile:v high -pix_fmt yuv420p");
	}
	else if (IsRHIDeviceNVIDIA())
	{
		Entrada = Fase == 0 ? TEXT("-hwaccel cuda -hwaccel_output_format cuda") : TEXT("");
		Filtro = Fase == 0 ? FString::Printf(TEXT("scale_cuda=w=%d:h=%d:force_original_aspect_ratio=decrease"), L, L) : FiltroCpu;
		Video = Fase == 0 ? TEXT("-c:v h264_nvenc -preset p5 -b:v 25M -maxrate 40M -profile:v high")
			: TEXT("-c:v h264_nvenc -preset p5 -b:v 25M -maxrate 40M -profile:v high -pix_fmt yuv420p");
	}
	else if (IsRHIDeviceAMD())
	{
		// d3d11va decodifica en cualquier fabricante; el escalado va en CPU (scale_d3d11 fallo en las pruebas).
		Entrada = Fase == 0 ? TEXT("-hwaccel d3d11va") : TEXT("");
		Filtro = FString::Printf(TEXT("scale=%d:%d:flags=bicubic,format=nv12"), W, H);
		Video = TEXT("-c:v h264_amf -usage transcoding -quality quality -rc vbr_peak -b:v 25M -maxrate 40M -profile:v high");
	}
	else
	{
		const bool bTodoGpu = Fase == 0 && DimOptimizarX > 0;
		Entrada = bTodoGpu ? TEXT("-hwaccel qsv -hwaccel_output_format qsv") : TEXT("");
		Filtro = bTodoGpu ? FString::Printf(TEXT("vpp_qsv=w=%d:h=%d"), W, H) : FString::Printf(TEXT("scale=%d:%d:flags=bicubic,format=nv12"), W, H);
		Video = TEXT("-c:v h264_qsv -preset slow -b:v 25M -maxrate 40M -profile:v high");
	}
	const FString Args = FString::Printf(
		TEXT("-y -hide_banner -loglevel error -nostats -progress \"%s\" %s -i \"%s\" -map 0:v:0 -map 0:a:0? -vf \"%s\" %s -c:a aac -ac 2 -b:a 192k -movflags +faststart \"%s\""),
		*ProgresoOptimizar, *Entrada, *EntradaOptimizar, *Filtro, *Video, *SalidaOptimizar);
	UE_LOG(LogDomoMedia, Display, TEXT("Optimizar (fase %d): %s %s"), Fase, *Ffmpeg, *Args);
	FaseOptimizar = Fase;
	// Prioridad baja para no trabar la proyeccion mientras se convierte.
	ProcOptimizar = FPlatformProcess::CreateProc(*Ffmpeg, *Args, false, true, true, nullptr, -1, nullptr, nullptr);
	return ProcOptimizar.IsValid();
}

bool ADomeMediaController::OptimizarVideoActual()
{
	if (bOptimizando)
	{
		Mensaje(TEXT("Ya se esta optimizando un video."));
		return false;
	}
	if (!Cues.IsValidIndex(CueActual))
	{
		Mensaje(TEXT("No hay video para optimizar."));
		return false;
	}
	const FDomeCue& C = Cues[CueActual];
	const FString Base = FPaths::ConvertRelativePathToFull(CarpetaPlaylist);
	FString Entrada = FPaths::IsRelative(C.Archivo) ? FPaths::Combine(Base, C.Archivo) : C.Archivo;
	Entrada = FPaths::ConvertRelativePathToFull(Entrada);
	FPaths::NormalizeFilename(Entrada);
	if (!FPaths::FileExists(Entrada))
	{
		Mensaje(TEXT("El archivo del video no existe."));
		return false;
	}
	const FString Carpeta = FPaths::Combine(Base, TEXT("optimizados"));
	IFileManager::Get().MakeDirectory(*Carpeta, true);
	EntradaOptimizar = Entrada;
	SalidaOptimizar = FPaths::Combine(Carpeta, FPaths::GetBaseFilename(Entrada) + FString::Printf(TEXT("_%d.mp4"), FMath::Clamp(LadoOptimizado, 512, 4096)));
	ProgresoOptimizar = FPaths::Combine(Carpeta, TEXT("progreso.txt"));
	DuracionOptimizar = MediaPlayer ? MediaPlayer->GetDuration().GetTotalSeconds() : 0.0;
	CueOptimizado = CueActual;
	if (FPaths::IsSamePath(Entrada, SalidaOptimizar))
	{
		Mensaje(TEXT("Este video ya es una copia optimizada."));
		return false;
	}
	{
		const FIntPoint Dim = MediaPlayer ? MediaPlayer->GetVideoTrackDimensions(INDEX_NONE, INDEX_NONE) : FIntPoint::ZeroValue;
		DimOptimizarX = Dim.X;
		DimOptimizarY = Dim.Y;
	}
	if (!LanzarFfmpeg(0))
	{
		return false;
	}
	bOptimizando = true;
	UltimoAvisoOptimizar = 0.0;
	Mensaje(FString::Printf(TEXT("Optimizando %s (lado %d). Sigue reproduciendo; al terminar se agrega a la lista."),
		*FPaths::GetCleanFilename(Entrada), FMath::Clamp(LadoOptimizado, 512, 4096)), 8.f);
	return true;
}

void ADomeMediaController::CancelarOptimizacion()
{
	if (ProcOptimizar.IsValid())
	{
		if (FPlatformProcess::IsProcRunning(ProcOptimizar))
		{
			FPlatformProcess::TerminateProc(ProcOptimizar, true);
		}
		FPlatformProcess::CloseProc(ProcOptimizar);
	}
	if (bOptimizando)
	{
		bOptimizando = false;
		IFileManager::Get().Delete(*SalidaOptimizar, false, true, true);
	}
}

void ADomeMediaController::ActualizarOptimizacion()
{
	if (!bOptimizando)
	{
		return;
	}
	if (FPlatformProcess::IsProcRunning(ProcOptimizar))
	{
		const double Ahora = FPlatformTime::Seconds();
		if (Ahora - UltimoAvisoOptimizar > 3.0)
		{
			UltimoAvisoOptimizar = Ahora;
			FString Texto;
			double Segundos = 0.0;
			if (FFileHelper::LoadFileToString(Texto, *ProgresoOptimizar, FFileHelper::EHashOptions::None, FILEREAD_AllowWrite))
			{
				int32 I = Texto.Find(TEXT("out_time_us="), ESearchCase::CaseSensitive, ESearchDir::FromEnd);
				if (I != INDEX_NONE)
				{
					Segundos = FCString::Atod(*Texto.Mid(I + 12)) / 1000000.0;
				}
			}
			const FString Avance = DuracionOptimizar > 1.0
				? FString::Printf(TEXT("%.0f %%"), FMath::Clamp(Segundos / DuracionOptimizar * 100.0, 0.0, 100.0))
				: FString::Printf(TEXT("%.0f s"), Segundos);
			Mensaje(FString::Printf(TEXT("Optimizando %s: %s"), *FPaths::GetCleanFilename(EntradaOptimizar), *Avance), 4.f);
		}
		return;
	}

	int32 Codigo = 0;
	FPlatformProcess::GetProcReturnCode(ProcOptimizar, &Codigo);
	FPlatformProcess::CloseProc(ProcOptimizar);
	const bool bExiste = FPaths::FileExists(SalidaOptimizar) && IFileManager::Get().FileSize(*SalidaOptimizar) > 100000;
	if (Codigo != 0 || !bExiste)
	{
		if (FaseOptimizar < 2)
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("Optimizar fase %d fallo (codigo %d); se reintenta con otra ruta."), FaseOptimizar, Codigo);
			Mensaje(FaseOptimizar == 0 ? TEXT("La ruta de GPU fallo; se reintenta decodificando en CPU.") : TEXT("El codificador de la GPU fallo; se reintenta con la CPU (mas lento)."), 6.f);
			if (LanzarFfmpeg(FaseOptimizar + 1))
			{
				return;
			}
		}
		bOptimizando = false;
		Mensaje(TEXT("No se pudo optimizar el video (ver el log)."), 10.f);
		return;
	}

	bOptimizando = false;
	if (Cues.IsValidIndex(CueOptimizado))
	{
		FDomeCue Nuevo = Cues[CueOptimizado];
		Nuevo.Nombre += TEXT(" (optimizado)");
		const FString Base = FPaths::ConvertRelativePathToFull(CarpetaPlaylist);
		FString Rel = SalidaOptimizar;
		Nuevo.Archivo = (FPaths::MakePathRelativeTo(Rel, *(Base / TEXT(""))) && !Rel.StartsWith(TEXT(".."))) ? Rel : SalidaOptimizar;
		Nuevo.bFormatoAuto = false;
		const int32 Indice = Cues.Add(Nuevo);
		if (Menu.IsValid())
		{
			Menu->RefrescarListas();
		}
		if (Fuente == EDomeFuente::Media)
		{
			GoToCue(Indice);
		}
		Mensaje(FString::Printf(TEXT("Listo: %s. Guardar lista lo deja en playlist.json."), *FPaths::GetCleanFilename(SalidaOptimizar)), 10.f);
	}
}

// --- Menu y lista de videos ---------------------------------------------------------

void ADomeMediaController::MostrarMenu(bool bVer)
{
	if (Menu.IsValid())
	{
		Menu->Mostrar(bVer);
	}
}

void ADomeMediaController::AlternarMenu()
{
	if (Menu.IsValid())
	{
		Menu->Alternar();
	}
}

bool ADomeMediaController::FotografiarMenu(const FString& Ruta, int32 Ancho, int32 Alto)
{
	return Menu.IsValid() && Menu->Fotografiar(Ruta, Ancho, Alto);
}

float ADomeMediaController::GetParam(FName Nombre) const
{
	{
		const FString Txt = Nombre.ToString();
		if (Txt.StartsWith(TEXT("S_")))
		{
			return GetCampoPantalla(Txt.Mid(2));
		}
	}
	if (Nombre == TEXT("Resplandor")) { return IntensidadResplandor; }
	if (Nombre == TEXT("LadoOptimizado")) { return static_cast<float>(LadoOptimizado); }
	if (Nombre == TEXT("Paredes")) { return static_cast<float>(ParedesModo); }
	if (Nombre == TEXT("RugosidadPiso")) { return RugosidadPiso; }
	if (Nombre == TEXT("VelCaminar")) { return Controles.VelocidadCaminar; }
	if (Nombre == TEXT("VelVuelo")) { return Controles.VelocidadVuelo; }
	if (Nombre == TEXT("MultCorrer")) { return Controles.MultiplicadorCorrer; }
	if (Nombre == TEXT("AlturaOjos")) { return Controles.AlturaOjos; }
	if (Nombre == TEXT("Sensibilidad")) { return Controles.Sensibilidad; }
	if (Nombre == TEXT("Gravedad")) { return Controles.Gravedad; }
	if (Nombre == DomoParam::Brillo)
	{
		return Brillo;
	}
	if (Nombre == DomoParam::FovSala)
	{
		return FovSala;
	}
	if (Cues.IsValidIndex(CueActual))
	{
		FDomeCue& C = const_cast<FDomeCue&>(Cues[CueActual]);
		if (const float* Campo = CampoDelCue(C, Nombre))
		{
			return *Campo;
		}
		if (Nombre == DomoParam::Formato)
		{
			return static_cast<float>(static_cast<uint8>(C.Formato));
		}
		if (Nombre == DomoParam::PantallaCurva)
		{
			return C.Pantalla.bCurva ? 1.f : 0.f;
		}
	}
	return 0.f;
}

void ADomeMediaController::SetLoop(bool bRepetir)
{
	if (Cues.IsValidIndex(CueActual))
	{
		Cues[CueActual].Loop = bRepetir;
	}
	if (MediaPlayer)
	{
		MediaPlayer->SetLooping(bRepetir);
	}
}

int32 ADomeMediaController::AgregarVideos(const TArray<FString>& Rutas)
{
	const FString Base = FPaths::ConvertRelativePathToFull(CarpetaPlaylist);
	auto RutaDelCue = [&](const FDomeCue& C)
	{
		FString R = FPaths::IsRelative(C.Archivo) ? FPaths::Combine(Base, C.Archivo) : C.Archivo;
		R = FPaths::ConvertRelativePathToFull(R);
		FPaths::NormalizeFilename(R);
		return R;
	};

	int32 Primero = INDEX_NONE;
	int32 Nuevos = 0;
	for (const FString& Ruta : Rutas)
	{
		FString Completa = FPaths::ConvertRelativePathToFull(Ruta);
		FPaths::NormalizeFilename(Completa);
		if (!FPaths::FileExists(Completa))
		{
			continue;
		}
		int32 Existente = Cues.IndexOfByPredicate([&](const FDomeCue& C) { return RutaDelCue(C).Equals(Completa, ESearchCase::IgnoreCase); });
		if (Existente == INDEX_NONE)
		{
			FDomeCue C;
			C.Nombre = FPaths::GetBaseFilename(Completa);
			FString Rel = Completa;
			C.Archivo = (FPaths::MakePathRelativeTo(Rel, *(Base / TEXT(""))) && !Rel.StartsWith(TEXT(".."))) ? Rel : Completa;
			EDomeFormato F = EDomeFormato::Plano169;
			if (FormatoPorNombre(C.Nombre, F))
			{
				C.Formato = F;
			}
			else
			{
				C.Formato = EDomeFormato::Plano169;
				C.bFormatoAuto = true;
			}
			Existente = Cues.Add(C);
			++Nuevos;
		}
		if (Primero == INDEX_NONE)
		{
			Primero = Existente;
		}
	}
	if (Primero == INDEX_NONE)
	{
		Mensaje(TEXT("No se agrego ningun video"));
		return 0;
	}
	if (Fuente != EDomeFuente::Media)
	{
		CueActual = Primero;
		SetFuente(EDomeFuente::Media);
	}
	else
	{
		GoToCue(Primero);
	}
	if (Menu.IsValid())
	{
		Menu->RefrescarListas();
	}
	Mensaje(FString::Printf(TEXT("%d video(s) agregado(s). Guardar lista los deja en playlist.json"), Nuevos));
	return Nuevos;
}

int32 ADomeMediaController::EscanearCarpeta()
{
	const FString Base = FPaths::ConvertRelativePathToFull(CarpetaPlaylist);
	TArray<FString> Archivos;
	IFileManager::Get().FindFiles(Archivos, *(Base / TEXT("*.*")), true, false);
	TArray<FString> Rutas;
	for (const FString& A : Archivos)
	{
		if (EsVideo(A))
		{
			Rutas.Add(FPaths::Combine(Base, A));
		}
	}
	Rutas.Sort();
	// Solo lo que aun no esta en la lista: AgregarVideos saltaria al primero aunque ya existiera.
	TArray<FString> Faltan;
	for (const FString& R : Rutas)
	{
		FString Completa = FPaths::ConvertRelativePathToFull(R);
		FPaths::NormalizeFilename(Completa);
		const bool bYa = Cues.ContainsByPredicate([&](const FDomeCue& C)
		{
			FString X = FPaths::IsRelative(C.Archivo) ? FPaths::Combine(Base, C.Archivo) : C.Archivo;
			X = FPaths::ConvertRelativePathToFull(X);
			FPaths::NormalizeFilename(X);
			return X.Equals(Completa, ESearchCase::IgnoreCase);
		});
		if (!bYa)
		{
			Faltan.Add(R);
		}
	}
	if (Faltan.Num() == 0)
	{
		Mensaje(TEXT("La carpeta no tiene videos nuevos"));
		return 0;
	}
	return AgregarVideos(Faltan);
}

bool ADomeMediaController::GuardarPlaylist()
{
	const FString Ruta = ResolverRutaPlaylist();
	if (!bCopiaHecha && FPaths::FileExists(Ruta))
	{
		IFileManager::Get().Copy(*(Ruta + TEXT(".bak")), *Ruta);
		bCopiaHecha = true;
	}

	TArray<TSharedPtr<FJsonValue>> Lista;
	for (const FDomeCue& C : Cues)
	{
		const TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("nombre"), C.Nombre);
		O->SetStringField(TEXT("archivo"), C.Archivo);
		O->SetStringField(TEXT("formato"), FormatoATexto(C.Formato));
		if (C.Yaw != 0.f) { O->SetNumberField(TEXT("yaw"), C.Yaw); }
		if (C.Pitch != 0.f) { O->SetNumberField(TEXT("pitch"), C.Pitch); }
		if (C.Roll != 0.f) { O->SetNumberField(TEXT("roll"), C.Roll); }
		if (C.Horizonte != 0.f) { O->SetNumberField(TEXT("horizonte"), C.Horizonte); }
		if (C.Curva != 1.f) { O->SetNumberField(TEXT("curva"), C.Curva); }
		if (C.FovContenido != 0.f) { O->SetNumberField(TEXT("fovContenido"), C.FovContenido); }
		if (C.Volumen != 1.f) { O->SetNumberField(TEXT("volumen"), C.Volumen); }
		O->SetBoolField(TEXT("loop"), C.Loop);
		if (C.Mapping.CentroX != 0.f || C.Mapping.CentroY != 0.f || C.Mapping.Escala != 1.f || C.Mapping.Rotar != 0.f)
		{
			const TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
			M->SetNumberField(TEXT("centroX"), C.Mapping.CentroX);
			M->SetNumberField(TEXT("centroY"), C.Mapping.CentroY);
			M->SetNumberField(TEXT("escala"), C.Mapping.Escala);
			M->SetNumberField(TEXT("rotar"), C.Mapping.Rotar);
			O->SetObjectField(TEXT("mapping"), M);
		}
		if (C.Formato == EDomeFormato::Plano169)
		{
			O->SetStringField(TEXT("plantilla"), C.Plantilla);
			if (C.GiroPantallas != 0.f) { O->SetNumberField(TEXT("giroPantallas"), C.GiroPantallas); }
			if (C.VelRecorrido != 0.f) { O->SetNumberField(TEXT("velRecorrido"), C.VelRecorrido); }
			if (C.VelGiro != 0.f) { O->SetNumberField(TEXT("velGiro"), C.VelGiro); }
			{
				const TSharedRef<FJsonObject> Fo = MakeShared<FJsonObject>();
				Fo->SetNumberField(TEXT("modo"), C.Fondo.Modo);
				Fo->SetNumberField(TEXT("desenfoque"), C.Fondo.Desenfoque);
				Fo->SetNumberField(TEXT("brillo"), C.Fondo.Brillo);
				Fo->SetNumberField(TEXT("saturacion"), C.Fondo.Saturacion);
				Fo->SetNumberField(TEXT("zoom"), C.Fondo.Zoom);
				Fo->SetNumberField(TEXT("repeticiones"), C.Fondo.Repeticiones);
				Fo->SetNumberField(TEXT("giro"), C.Fondo.Giro);
				O->SetObjectField(TEXT("fondo"), Fo);
			}
			TArray<TSharedPtr<FJsonValue>> Filas;
			for (const FDomePantallaFila& F : C.Pantallas)
			{
				const TSharedRef<FJsonObject> P = MakeShared<FJsonObject>();
				P->SetStringField(TEXT("nombre"), F.Nombre);
				P->SetBoolField(TEXT("encendida"), F.bEncendida);
				P->SetStringField(TEXT("forma"), FormaATexto(F.Forma));
				P->SetNumberField(TEXT("yaw"), F.Yaw);
				P->SetNumberField(TEXT("elevacion"), F.Elevacion);
				P->SetNumberField(TEXT("roll"), F.Roll);
				P->SetNumberField(TEXT("ancho"), F.Ancho);
				P->SetNumberField(TEXT("alto"), F.Alto);
				P->SetStringField(TEXT("espejo"), EspejoATexto(F.Espejo));
				P->SetNumberField(TEXT("opacidad"), F.Opacidad);
				P->SetNumberField(TEXT("cropX"), F.CropX);
				P->SetNumberField(TEXT("cropY"), F.CropY);
				P->SetNumberField(TEXT("cropW"), F.CropW);
				P->SetNumberField(TEXT("cropH"), F.CropH);
				P->SetNumberField(TEXT("borde"), F.Borde);
				P->SetNumberField(TEXT("repeticion"), F.Repeticion);
				P->SetNumberField(TEXT("solape"), F.Solape);
				P->SetNumberField(TEXT("copias"), F.Copias);
				P->SetNumberField(TEXT("arco"), F.Arco);
				P->SetBoolField(TEXT("espejoAlterno"), F.bEspejoAlterno);
				P->SetNumberField(TEXT("corrimiento"), F.Corrimiento);
				P->SetStringField(TEXT("bordes"), BordesATexto(F.Bordes));
				P->SetNumberField(TEXT("recorrido"), F.Recorrido);
				P->SetNumberField(TEXT("giro"), F.Giro);
				if (F.Brillo != 0.f) { P->SetNumberField(TEXT("brillo"), F.Brillo); }
				Filas.Add(MakeShared<FJsonValueObject>(P));
			}
			O->SetArrayField(TEXT("pantallas"), Filas);
		}
		Lista.Add(MakeShared<FJsonValueObject>(O));
	}

	const TSharedRef<FJsonObject> Raiz = MakeShared<FJsonObject>();
	if (!NotaEnJson.IsEmpty())
	{
		Raiz->SetStringField(TEXT("_nota"), NotaEnJson);
	}
	if (!CarpetaEnJson.IsEmpty())
	{
		Raiz->SetStringField(TEXT("carpeta"), CarpetaEnJson);
	}
	Raiz->SetArrayField(TEXT("cues"), Lista);

	FString Texto;
	const TSharedRef<TJsonWriter<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>> Escritor =
		TJsonWriterFactory<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>::Create(&Texto);
	if (!FJsonSerializer::Serialize(Raiz, Escritor))
	{
		Mensaje(TEXT("No se pudo armar el JSON de la playlist"), 6.f);
		return false;
	}
	Escritor->Close();
	const bool bOk = FFileHelper::SaveStringToFile(Texto, *Ruta, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	Mensaje(bOk ? FString::Printf(TEXT("Lista guardada: %s"), *Ruta) : FString::Printf(TEXT("No se pudo escribir %s"), *Ruta), 6.f);
	return bOk;
}

void ADomeMediaController::ActualizarFormatoAuto()
{
	if (!bFormatoPendiente || !MediaPlayer || !Cues.IsValidIndex(CueActual) || !Cues[CueActual].bFormatoAuto)
	{
		return;
	}
	if (!MediaPlayer->IsReady())
	{
		return;
	}
	const FIntPoint D = MediaPlayer->GetVideoTrackDimensions(INDEX_NONE, INDEX_NONE);
	if (D.X <= 0 || D.Y <= 0)
	{
		return;
	}
	bFormatoPendiente = false;
	FDomeCue& C = Cues[CueActual];
	C.bFormatoAuto = false;
	const float Razon = static_cast<float>(D.X) / static_cast<float>(D.Y);
	if (FMath::Abs(Razon - 1.f) < 0.1f)
	{
		C.Formato = EDomeFormato::Domemaster;
	}
	else if (Razon > 1.9f && Razon < 2.1f)
	{
		C.Formato = EDomeFormato::Equirect360;
	}
	else
	{
		C.Formato = EDomeFormato::Plano169;
	}
	AplicarParametros(C);
	Mensaje(FString::Printf(TEXT("%s: %dx%d, formato %s (se cambia en Imagen en la cupula)"),
		*C.Nombre, D.X, D.Y, FormatoATexto(C.Formato)));
}

void ADomeMediaController::IrAVista(const FVector& Ubicacion, const FRotator& Rotacion, const FString& Nombre)
{
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (!PC)
	{
		return;
	}
	if (ADomePawn* J = Cast<ADomePawn>(PC->GetPawn()))
	{
		J->IrAOjos(Ubicacion, Rotacion);
		Controles.Modo = EDomeModoMovimiento::Volar;
	}
	else if (APawn* P = PC->GetPawn())
	{
		P->SetActorLocation(Ubicacion, false, nullptr, ETeleportType::TeleportPhysics);
		P->SetActorRotation(Rotacion);
	}
	PC->SetControlRotation(Rotacion);
	Mensaje(FString::Printf(TEXT("Vista: %s (modo volar; F vuelve a caminar)"), *Nombre));
}

// --- Perfiles de render, sala y ajustes guardados ---------------------------------------------

FString ADomeMediaController::ElegirPerfilAuto() const
{
	if (GEngine && GEngine->XRSystem.IsValid())
	{
		IHeadMountedDisplay* Hmd = GEngine->XRSystem->GetHMDDevice();
		if (Hmd && Hmd->IsHMDEnabled()) { return TEXT("vr"); }
	}
	const uint64 Vram = GRHIGlobals.GpuInfo.DedicatedVideoMemory;
	const bool bRt = GRHISupportsRayTracing;
	const bool bIntegrada = GRHIDeviceIsIntegrated || (Vram > 0 && Vram < (3ull << 30));
	if (bIntegrada) { return TEXT("ligero"); }
	// Con trazado de rayos por hardware y 8 GB o mas (RTX, RDNA2 o mas nuevo, Arc): perfil de monitor.
	if (bRt && Vram >= (8ull << 30)) { return TEXT("monitor"); }
	return TEXT("ligero");
}

void ADomeMediaController::AplicarPerfil(const FString& IdPedido)
{
	FString Id = IdPedido.TrimStartAndEnd().ToLower();
	if (Id == TEXT("render")) { Id = TEXT("proyector"); }
	if (Id.IsEmpty()) { Id = TEXT("auto"); }
	const FString Resuelto = Id == TEXT("auto") ? ElegirPerfilAuto() : Id;
	const DomoPerfil::FDatos* D = DomoPerfil::Buscar(Resuelto);
	if (!D)
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("Perfil desconocido '%s' (auto, vr, monitor, proyector o ligero)."), *IdPedido);
		return;
	}
	PerfilActual = Id;
	PerfilResuelto = D->Id;
	UltimaResolucion = DomoPerfil::TamanoVentana();
	DomoPerfil::Aplicar(*D);
	MarcarAjustes();
	UE_LOG(LogDomoMedia, Display, TEXT("%s"), *DescribirPerfil());
	Mensaje(FString::Printf(TEXT("Calidad: %s"), D->Nombre), 3.f);
}

void ADomeMediaController::AplicarResolucionInterna()
{
	const DomoPerfil::FDatos* D = DomoPerfil::Buscar(PerfilResuelto);
	if (!D) { return; }
	UltimaResolucion = DomoPerfil::TamanoVentana();
	const int32 Sp = DomoPerfil::PorcentajeDePantalla(*D);
	DomoPerfil::PonerCVar(TEXT("r.ScreenPercentage"), FString::FromInt(Sp));
	DomoPerfil::PonerCVar(TEXT("r.TSR.History.ScreenPercentage"), FString::FromInt(FMath::Max(Sp, 100)));
}

FString ADomeMediaController::DescribirPerfil() const
{
	const DomoPerfil::FDatos* D = DomoPerfil::Buscar(PerfilResuelto);
	const FIntPoint V = DomoPerfil::TamanoVentana();
	const int32 Sp = D ? DomoPerfil::PorcentajeDePantalla(*D) : 100;
	const uint64 Vram = GRHIGlobals.GpuInfo.DedicatedVideoMemory;
	const TCHAR* Fabricante = IsRHIDeviceNVIDIA() ? TEXT("NVIDIA") : IsRHIDeviceAMD() ? TEXT("AMD") : IsRHIDeviceIntel() ? TEXT("Intel") : TEXT("otro");
	const FString Tarjeta = GRHIAdapterName.Contains(Fabricante) ? GRHIAdapterName : FString::Printf(TEXT("%s %s"), Fabricante, *GRHIAdapterName);
	return FString::Printf(TEXT("Perfil %s (%s) en %s, %d MB de video, trazado de rayos %s; ventana %dx%d a %d %%"),
		D ? D->Nombre : TEXT("sin aplicar"), *PerfilActual, *Tarjeta, static_cast<int32>(Vram >> 20),
		GRHISupportsRayTracing ? TEXT("si") : TEXT("no"), V.X, V.Y, Sp);
}

void ADomeMediaController::RecogerSala()
{
	UWorld* Mundo = GetWorld();
	if (!Mundo) { return; }
	MatsSala.Reset();
	for (TActorIterator<AActor> It(Mundo); It; ++It)
	{
		TArray<UStaticMeshComponent*> Mallas;
		It->GetComponents<UStaticMeshComponent>(Mallas);
		for (UStaticMeshComponent* M : Mallas)
		{
			for (int32 i = 0; i < M->GetNumMaterials(); ++i)
			{
				UMaterialInterface* Mat = M->GetMaterial(i);
				if (!Mat) { continue; }
				const FString N = Mat->GetName();
				int32 Tipo = -1;
				if (N == TEXT("MI_Muro")) { Tipo = 0; }
				else if (N == TEXT("MI_Madera")) { Tipo = 1; }
				else if (N == TEXT("MI_Piso")) { Tipo = 2; }
				if (Tipo < 0) { continue; }
				if (UMaterialInstanceDynamic* Mid = M->CreateDynamicMaterialInstance(i, Mat))
				{
					FMatSala F;
					F.Mid = Mid;
					F.Tipo = Tipo;
					F.TinteOriginal = Mid->K2_GetVectorParameterValue(TEXT("Tinte"));
					F.RugOriginal = Mid->K2_GetScalarParameterValue(TEXT("RugMul"));
					MatsSala.Add(F);
				}
			}
		}
	}
	bSalaRecogida = true;
	UE_LOG(LogDomoMedia, Display, TEXT("Sala: %d materiales de muro, listones y piso."), MatsSala.Num());
	AplicarSala();
}

void ADomeMediaController::AplicarSala()
{
	if (!bSalaRecogida) { return; }
	static const FLinearColor Negro(0.008f, 0.008f, 0.010f, 1.f);
	for (const FMatSala& F : MatsSala)
	{
		UMaterialInstanceDynamic* Mid = F.Mid.Get();
		if (!Mid) { continue; }
		if (F.Tipo == 2)
		{
			Mid->SetScalarParameterValue(TEXT("RugMul"), F.RugOriginal * RugosidadPiso);
		}
		else
		{
			Mid->SetVectorParameterValue(TEXT("Tinte"), ParedesModo == 0 ? Negro : F.TinteOriginal);
		}
	}
}

FString ADomeMediaController::RutaAjustes() const
{
	return FPaths::Combine(FPaths::ConvertRelativePathToFull(CarpetaPlaylist), TEXT("ajustes.json"));
}

void ADomeMediaController::MarcarAjustes()
{
	bAjustesSucios = true;
	UltimoCambioAjustes = FPlatformTime::Seconds();
}

void ADomeMediaController::GuardarAjustes()
{
	bAjustesSucios = false;
	const TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetStringField(TEXT("_nota"), TEXT("Ajustes del ejecutable: los escribe el menu. Se pueden editar a mano con el programa cerrado."));
	O->SetStringField(TEXT("perfil"), PerfilActual);
	O->SetNumberField(TEXT("paredes"), ParedesModo);
	O->SetNumberField(TEXT("rugosidadPiso"), RugosidadPiso);
	O->SetNumberField(TEXT("resplandor"), IntensidadResplandor);
	O->SetStringField(TEXT("luces"), bLucesAutomaticas ? TEXT("auto") : (bLucesEncendidas ? TEXT("on") : TEXT("off")));
	O->SetStringField(TEXT("reproductor"), Reproductor.IsNone() ? TEXT("auto") : *Reproductor.ToString());
	O->SetNumberField(TEXT("ladoOptimizado"), LadoOptimizado);
	FString Texto;
	const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Texto);
	if (!FJsonSerializer::Serialize(O, W) || !FFileHelper::SaveStringToFile(Texto, *RutaAjustes(), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("No se pudo escribir %s"), *RutaAjustes());
	}
}

void ADomeMediaController::CargarAjustes()
{
	FString Texto;
	if (FFileHelper::LoadFileToString(Texto, *RutaAjustes()))
	{
		TSharedPtr<FJsonObject> O;
		if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Texto), O) && O.IsValid())
		{
			O->TryGetStringField(TEXT("perfil"), PerfilActual);
			double N = 0.0;
			if (O->TryGetNumberField(TEXT("paredes"), N)) { ParedesModo = N > 0.5 ? 1 : 0; }
			if (O->TryGetNumberField(TEXT("rugosidadPiso"), N)) { RugosidadPiso = FMath::Clamp(static_cast<float>(N), 0.2f, 6.f); }
			if (O->TryGetNumberField(TEXT("resplandor"), N)) { IntensidadResplandor = FMath::Max(static_cast<float>(N), 0.f); UltimoResplandor = -1.f; }
			if (O->TryGetNumberField(TEXT("ladoOptimizado"), N)) { LadoOptimizado = FMath::Clamp(FMath::RoundToInt(static_cast<float>(N)), 512, 4096); }
			FString S;
			if (O->TryGetStringField(TEXT("luces"), S))
			{
				if (S == TEXT("on")) { bLucesAutomaticas = false; bLucesEncendidas = true; }
				else if (S == TEXT("off")) { bLucesAutomaticas = false; bLucesEncendidas = false; }
				else { bLucesAutomaticas = true; }
			}
			if (O->TryGetStringField(TEXT("reproductor"), S) && !S.IsEmpty())
			{
				Reproductor = S.Equals(TEXT("auto"), ESearchCase::IgnoreCase) ? NAME_None : FName(*S);
			}
			UE_LOG(LogDomoMedia, Display, TEXT("Ajustes leidos de %s"), *RutaAjustes());
		}
	}
	bAjustesSucios = false;
	FString Forzado;
	if (!GIsEditor && !FParse::Value(FCommandLine::Get(), TEXT("DomoPreset="), Forzado))
	{
		AplicarPerfil(PerfilActual);
		bAjustesSucios = false;
	}
}

// --- Teclas y movimiento ---------------------------------------------------------------

bool ADomeMediaController::MenuVisible() const
{
	return Menu.IsValid() && Menu->EstaVisible();
}

FString ADomeMediaController::RutaControles() const
{
	return FPaths::Combine(FPaths::ConvertRelativePathToFull(CarpetaPlaylist), TEXT("controles.json"));
}

void ADomeMediaController::GuardarControles()
{
	bControlesSucios = false;
	if (!Controles.Guardar(RutaControles()))
	{
		UE_LOG(LogDomoMedia, Warning, TEXT("No se pudo escribir %s"), *RutaControles());
	}
}

void ADomeMediaController::AplicarMovimiento()
{
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (ADomePawn* J = PC ? Cast<ADomePawn>(PC->GetPawn()) : nullptr)
	{
		J->AplicarAjustes(Controles);
	}
	bControlesSucios = true;
	UltimoCambioControles = FPlatformTime::Seconds();
}

void ADomeMediaController::PonerModoMovimiento(EDomeModoMovimiento Modo)
{
	Controles.Modo = Modo;
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (ADomePawn* J = PC ? Cast<ADomePawn>(PC->GetPawn()) : nullptr)
	{
		J->PonerModo(Modo);
	}
	bControlesSucios = true;
	UltimoCambioControles = FPlatformTime::Seconds();
	Mensaje(Modo == EDomeModoMovimiento::Caminar ? TEXT("Modo: caminar")
		: Modo == EDomeModoMovimiento::Volar ? TEXT("Modo: volar") : TEXT("Modo: fantasma (atraviesa todo)"));
}

void ADomeMediaController::RestablecerControles(bool bTeclas, bool bMovimiento)
{
	if (bTeclas) { Controles.RestablecerTeclas(); }
	if (bMovimiento) { Controles.RestablecerMovimiento(); }
	AplicarMovimiento();
	Mensaje(TEXT("Controles restablecidos"));
}

void ADomeMediaController::IrAlInicio()
{
	UWorld* Mundo = GetWorld();
	APlayerController* PC = Mundo ? Mundo->GetFirstPlayerController() : nullptr;
	ADomePawn* J = PC ? Cast<ADomePawn>(PC->GetPawn()) : nullptr;
	if (!J)
	{
		return;
	}
	AActor* Inicio = UGameplayStatics::GetActorOfClass(Mundo, APlayerStart::StaticClass());
	if (Inicio)
	{
		J->SetActorLocation(Inicio->GetActorLocation(), false, nullptr, ETeleportType::TeleportPhysics);
		PC->SetControlRotation(Inicio->GetActorRotation());
	}
	PonerModoMovimiento(EDomeModoMovimiento::Caminar);
}

void ADomeMediaController::EsperarTecla(EDomeAccion Accion, int32 Ranura)
{
	AccionEsperando = static_cast<int32>(Accion);
	RanuraEsperando = Ranura;
	Mensaje(FString::Printf(TEXT("Pulsa la tecla para \"%s\" (Esc cancela, Supr la borra)"), FDomeControles::Info(Accion).Etiqueta), 30.f);
}

void ADomeMediaController::CancelarEsperaDeTecla()
{
	AccionEsperando = -1;
}

void ADomeMediaController::CapturarTecla(APlayerController* PC)
{
	TArray<FKey> Todas;
	EKeys::GetAllKeys(Todas);
	for (const FKey& K : Todas)
	{
		if (!K.IsValid() || K.IsMouseButton() || K.IsGamepadKey() || K.IsTouch() || K.IsAxis1D() || K.IsAxis2D() || K.IsAxis3D())
		{
			continue;
		}
		if (!PC->WasInputKeyJustPressed(K))
		{
			continue;
		}
		const EDomeAccion Accion = static_cast<EDomeAccion>(AccionEsperando);
		if (K == EKeys::Escape)
		{
			CancelarEsperaDeTecla();
			Mensaje(TEXT("Cancelado"));
			return;
		}
		if (K == EKeys::Delete || K == EKeys::BackSpace)
		{
			Controles.PonerTecla(Accion, RanuraEsperando, FKey());
		}
		else
		{
			Controles.PonerTecla(Accion, RanuraEsperando, K);
		}
		CancelarEsperaDeTecla();
		bControlesSucios = true;
		UltimoCambioControles = FPlatformTime::Seconds();
		Mensaje(FString::Printf(TEXT("%s: %s"), FDomeControles::Info(Accion).Etiqueta, *Controles.Texto(Accion, RanuraEsperando)));
		return;
	}
}

void ADomeMediaController::ProcesarTeclas()
{
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (!PC)
	{
		return;
	}
	if (AccionEsperando >= 0)
	{
		CapturarTecla(PC);
		return;
	}
	if (!bControlTeclado)
	{
		return;
	}
	const FDomeControles& K = Controles;
	if (K.RecienApretada(EDomeAccion::Menu, PC)) { AlternarMenu(); }
	if (K.RecienApretada(EDomeAccion::Siguiente, PC)) { Next(); }
	if (K.RecienApretada(EDomeAccion::Anterior, PC)) { Prev(); }
	if (K.RecienApretada(EDomeAccion::Negro, PC)) { ToggleBlackout(); }
	if (K.RecienApretada(EDomeAccion::Pausa, PC)) { TogglePause(); }
	if (K.RecienApretada(EDomeAccion::Reiniciar, PC)) { Reiniciar(); }
	if (K.RecienApretada(EDomeAccion::Fuente, PC)) { ToggleFuente(); }
	if (K.RecienApretada(EDomeAccion::Ayuda, PC)) { TeclaAyuda(); }
	if (K.RecienApretada(EDomeAccion::CambiarModo, PC))
	{
		const EDomeModoMovimiento Siguiente_ = Controles.Modo == EDomeModoMovimiento::Caminar ? EDomeModoMovimiento::Volar
			: Controles.Modo == EDomeModoMovimiento::Volar ? EDomeModoMovimiento::Fantasma : EDomeModoMovimiento::Caminar;
		PonerModoMovimiento(Siguiente_);
	}
	static const FKey Numeros[] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five,
		EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine };
	for (int32 i = 0; i < UE_ARRAY_COUNT(Numeros); ++i)
	{
		if (PC->WasInputKeyJustPressed(Numeros[i]))
		{
			GoToCue(i);
		}
	}
}

// --- Teclado, mensajes y guion ------------------------------------------------

void ADomeMediaController::ConfigurarTeclado()
{
	// Las teclas se leen por sondeo (ProcesarTeclas) contra FDomeControles: no hay
	// nada que cablear, y el menu puede cambiarlas en vivo.
}

void ADomeMediaController::TeclaAyuda()
{
	Mensaje(FString::Printf(TEXT("WASD moverse   F: caminar/volar/fantasma   1-9: cue   Flechas: video   B: negro   Espacio: pausa   F3: Spout/Media   F2 o M: menu (%s para cambiar las teclas)"), TEXT("Movimiento y teclas")), 8.f);
	Mensaje(DescribirEstado(), 8.f);
}

void ADomeMediaController::Mensaje(const FString& Texto, float Segundos) const
{
	UE_LOG(LogDomoMedia, Display, TEXT("%s"), *Texto);
	const_cast<ADomeMediaController*>(this)->UltimoMensaje = Texto;
	if (GEngine && EsMundoDeJuego())
	{
		GEngine->AddOnScreenDebugMessage(-1, Segundos, FColor(120, 220, 255), Texto);
	}
}

void ADomeMediaController::CorrerGuion(float DeltaSeconds)
{
	if (LineaGuion >= Guion.Num())
	{
		return;
	}
	if (EsperaGuion > 0.f)
	{
		EsperaGuion -= DeltaSeconds;
		return;
	}
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	while (LineaGuion < Guion.Num() && EsperaGuion <= 0.f)
	{
		const FString Linea = Guion[LineaGuion++].TrimStartAndEnd();
		if (Linea.IsEmpty() || Linea.StartsWith(TEXT("#")))
		{
			continue;
		}
		UE_LOG(LogDomoMedia, Display, TEXT("Guion> %s"), *Linea);
		FString Resto;
		if (Linea.Split(TEXT(" "), nullptr, &Resto) && Linea.StartsWith(TEXT("esperar")))
		{
			EsperaGuion = FCString::Atof(*Resto);
			continue;
		}
		if (PC)
		{
			PC->ConsoleCommand(Linea, true);
		}
		else if (GEngine)
		{
			GEngine->Exec(GetWorld(), *Linea);
		}
	}
}

#if WITH_EDITOR
void ADomeMediaController::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	Super::PostEditChangeProperty(PropertyChangedEvent);
	const FName Prop = PropertyChangedEvent.GetPropertyName();
	if (!bInicializado)
	{
		return;
	}
	if (Prop == GET_MEMBER_NAME_CHECKED(ADomeMediaController, Fuente))
	{
		AplicarFuente();
	}
	else if (Prop == GET_MEMBER_NAME_CHECKED(ADomeMediaController, FovSala) && Cues.IsValidIndex(CueActual))
	{
		AplicarParametros(Cues[CueActual]);
	}
}
#endif

ADomeMediaController* ADomeMediaController::Buscar(UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<ADomeMediaController> It(World); It; ++It)
	{
		return *It;
	}
	return nullptr;
}

// --- Comandos de consola domo.* -----------------------------------------------
// Sirven para operar desde la consola (tecla ~), desde un guion de prueba
// (-DomoGuion=) y desde Remote Control. En el build Development la consola esta
// disponible; en Shipping no.

namespace
{
	template <typename TFunc>
	void ConControlador(UWorld* World, TFunc&& Func)
	{
		if (ADomeMediaController* C = ADomeMediaController::Buscar(World))
		{
			Func(*C);
		}
		else
		{
			UE_LOG(LogDomoMedia, Warning, TEXT("No hay DomeMediaController en este nivel."));
		}
	}

	FAutoConsoleCommandWithWorldAndArgs CmdCue(TEXT("domo.Cue"), TEXT("domo.Cue N: ir al cue N (desde 1)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C) { C.GoToCue(A.Num() > 0 ? FCString::Atoi(*A[0]) - 1 : 0); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSiguiente(TEXT("domo.Siguiente"), TEXT("Siguiente cue."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.Next(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAnterior(TEXT("domo.Anterior"), TEXT("Cue anterior."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.Prev(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdNegro(TEXT("domo.Negro"), TEXT("domo.Negro [0|1]: fundido a negro (sin argumento, alterna)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() > 0) { C.Blackout(FCString::Atoi(*A[0]) != 0); }
				else { C.ToggleBlackout(); }
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdLuces(TEXT("domo.Luces"),
		TEXT("domo.Luces 0|1|auto: apaga o enciende las luces de la sala; auto las hace seguir a la senal."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() == 0 || A[0].Equals(TEXT("auto"), ESearchCase::IgnoreCase)) { C.LucesAutomaticas(true); }
				else { C.SetLuces(FCString::Atoi(*A[0]) != 0); }
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMenu(TEXT("domo.Menu"), TEXT("domo.Menu [0|1]: muestra u oculta el menu en pantalla (sin argumento, alterna)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() > 0) { C.MostrarMenu(FCString::Atoi(*A[0]) != 0); }
				else { C.AlternarMenu(); }
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAbrir(TEXT("domo.Abrir"), TEXT("domo.Abrir RutaCompleta: agrega el video a la lista y lo pone en la cupula."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (A.Num() == 0) { return; }
			// Las rutas con espacios llegan partidas por la consola: se vuelven a unir.
			const FString Ruta = FString::Join(A, TEXT(" "));
			ConControlador(W, [&](ADomeMediaController& C) { C.AbrirVideoPorRuta(Ruta.TrimQuotes()); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSender(TEXT("domo.Sender"), TEXT("domo.Sender Nombre: sender de Spout a recibir."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (A.Num() == 0) { return; }
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (C.SpoutReceiver) { C.SpoutReceiver->SpoutSenderName = FName(*FString::Join(A, TEXT(" "))); }
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdGuardar(TEXT("domo.Guardar"), TEXT("Escribe la playlist con los ajustes actuales."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.GuardarPlaylist(); C.GuardarAjustes(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOptimizar(TEXT("domo.Optimizar"), TEXT("Hace una copia liviana (H.264, 2048) del video actual con ffmpeg y la agrega a la lista."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() > 0) { C.LadoOptimizado = FCString::Atoi(*A[0]); }
				C.OptimizarVideoActual();
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPerfil(TEXT("domo.Perfil"), TEXT("domo.Perfil auto|vr|monitor|proyector|ligero: perfil de render segun la pantalla y la tarjeta (sin argumento, describe el actual)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() > 0) { C.AplicarPerfil(A[0]); }
				UE_LOG(LogDomoMedia, Display, TEXT("%s"), *C.DescribirPerfil());
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdParedes(TEXT("domo.Paredes"), TEXT("domo.Paredes 0|1: paredes de la sala negras (0) o con la madera original (1)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C) { C.SetParam(TEXT("Paredes"), A.Num() > 0 ? static_cast<float>(FCString::Atoi(*A[0])) : 0.f); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdReproductor(TEXT("domo.Reproductor"), TEXT("domo.Reproductor auto|electra|protron|wmf: elige el decodificador de video (electra y protron usan la GPU con DX12)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C) { C.PonerReproductor(A.Num() > 0 ? A[0] : TEXT("auto")); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPlantilla(TEXT("domo.Plantilla"), TEXT("domo.Plantilla id: montaje de pantallas 16:9 (cine, sala_2, sala_4, sala_corona, tunel, anillo, cilindro...)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (A.Num() == 0) { return; }
			ConControlador(W, [&](ADomeMediaController& C) { C.AplicarPlantilla(A[0]); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdModo(TEXT("domo.Modo"), TEXT("domo.Modo caminar|volar|fantasma: como se mueve el jugador."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				const FString M = A.Num() > 0 ? A[0].ToLower() : FString(TEXT("caminar"));
				C.PonerModoMovimiento(M == TEXT("volar") ? EDomeModoMovimiento::Volar
					: M == TEXT("fantasma") ? EDomeModoMovimiento::Fantasma : EDomeModoMovimiento::Caminar);
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdInicio(TEXT("domo.Inicio"), TEXT("Vuelve al jugador al PlayerStart, caminando."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.IrAlInicio(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSuelo(TEXT("domo.Suelo"), TEXT("Traza hacia abajo desde el jugador y escribe en el log todo lo que toca (diagnostico de colisiones)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			APlayerController* PC = W ? W->GetFirstPlayerController() : nullptr;
			APawn* P = PC ? PC->GetPawn() : nullptr;
			if (!P) { return; }
			const FVector Pos = P->GetActorLocation();
			const ECollisionChannel Canales[] = { ECC_Visibility, ECC_Pawn, ECC_WorldStatic };
			const TCHAR* Nombres[] = { TEXT("Visibility"), TEXT("Pawn"), TEXT("WorldStatic") };
			for (int32 c = 0; c < 3; ++c)
			{
				for (int32 complejo = 0; complejo < 2; ++complejo)
				{
					TArray<FHitResult> Golpes;
					FCollisionQueryParams Params(SCENE_QUERY_STAT(DomoSuelo), complejo == 1, P);
					W->LineTraceMultiByChannel(Golpes, FVector(Pos.X, Pos.Y, 600.f), FVector(Pos.X, Pos.Y, -1500.f), Canales[c], Params);
					UE_LOG(LogDomoMedia, Display, TEXT("Suelo en (%.0f, %.0f) canal %s complejo=%d: %d golpes"), Pos.X, Pos.Y, Nombres[c], complejo, Golpes.Num());
					for (const FHitResult& H : Golpes)
					{
						UE_LOG(LogDomoMedia, Display, TEXT("  z=%.1f %s"), H.ImpactPoint.Z, H.GetActor() ? *H.GetActor()->GetName() : TEXT("?"));
					}
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPosicion(TEXT("domo.Posicion"), TEXT("Escribe en el log donde esta el jugador (ojos y pies)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			APlayerController* PC = W ? W->GetFirstPlayerController() : nullptr;
			if (APawn* P = PC ? PC->GetPawn() : nullptr)
			{
				const FVector Ojos = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : P->GetActorLocation();
				UE_LOG(LogDomoMedia, Display, TEXT("Posicion: pawn %s centro %s ojos z=%.1f cm"), *P->GetClass()->GetName(), *P->GetActorLocation().ToString(), Ojos.Z);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMenuFoto(TEXT("domo.MenuFoto"), TEXT("domo.MenuFoto Ruta.png [Ancho Alto]: dibuja el menu en un PNG (verificacion)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() == 0) { return; }
				const bool bOk = C.FotografiarMenu(A[0], A.Num() > 1 ? FCString::Atoi(*A[1]) : 500, A.Num() > 2 ? FCString::Atoi(*A[2]) : 1000);
				UE_LOG(LogDomoMedia, Display, TEXT("MenuFoto %s: %s"), *A[0], bOk ? TEXT("ok") : TEXT("fallo"));
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPausa(TEXT("domo.Pausa"), TEXT("Pausa o play."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.TogglePause(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdParam(TEXT("domo.Param"), TEXT("domo.Param Nombre Valor: Yaw, Pitch, Roll, Horizonte, Curva, FovContenido, CentroX, CentroY, Escala, Rotar, Formato, Brillo, Volumen, Pantalla*."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			if (A.Num() < 2)
			{
				UE_LOG(LogDomoMedia, Warning, TEXT("Uso: domo.Param Nombre Valor"));
				return;
			}
			ConControlador(W, [&](ADomeMediaController& C) { C.SetParam(FName(*A[0]), FCString::Atof(*A[1])); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdFuente(TEXT("domo.Fuente"), TEXT("domo.Fuente Spout|Media (sin argumento, alterna)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			ConControlador(W, [&](ADomeMediaController& C)
			{
				if (A.Num() == 0) { C.ToggleFuente(); }
				else { C.SetFuente(A[0].Equals(TEXT("Spout"), ESearchCase::IgnoreCase) ? EDomeFuente::Spout : EDomeFuente::Media); }
			});
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPreset(TEXT("domo.Preset"), TEXT("domo.Preset VR|Render: calidad liviana para el visor o de captura."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld*)
		{
			ADomeMediaController::AplicarPreset(A.Num() > 0 ? A[0] : FString(TEXT("VR")));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRecargar(TEXT("domo.Recargar"), TEXT("Vuelve a leer la playlist."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { C.RecargarPlaylist(); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdEstado(TEXT("domo.Estado"), TEXT("Escribe en el log el estado del reproductor."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* W)
		{
			ConControlador(W, [](ADomeMediaController& C) { UE_LOG(LogDomoMedia, Display, TEXT("Estado: %s"), *C.DescribirEstado()); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCamara(TEXT("domo.Camara"),
		TEXT("domo.Camara X Y Z Pitch Yaw [FOV]: mueve al jugador (cm, grados). Para capturas de verificacion."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& A, UWorld* W)
		{
			APlayerController* PC = W ? W->GetFirstPlayerController() : nullptr;
			if (!PC || A.Num() < 5)
			{
				UE_LOG(LogDomoMedia, Warning, TEXT("Uso: domo.Camara X Y Z Pitch Yaw [FOV] (en un mundo de juego)"));
				return;
			}
			const FVector Pos(FCString::Atof(*A[0]), FCString::Atof(*A[1]), FCString::Atof(*A[2]));
			const FRotator Rot(FCString::Atof(*A[3]), FCString::Atof(*A[4]), 0.f);
			if (ADomePawn* J = Cast<ADomePawn>(PC->GetPawn()))
			{
				J->IrAOjos(Pos, Rot);
			}
			else if (APawn* P = PC->GetPawn())
			{
				P->SetActorLocation(Pos, false, nullptr, ETeleportType::TeleportPhysics);
				P->SetActorRotation(Rot);
			}
			PC->SetControlRotation(Rot);
			if (A.Num() > 5 && PC->PlayerCameraManager)
			{
				PC->PlayerCameraManager->SetFOV(FCString::Atof(*A[5]));
			}
		}));
}
