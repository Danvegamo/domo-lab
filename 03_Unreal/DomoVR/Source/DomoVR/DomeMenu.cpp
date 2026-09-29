#include "DomeMenu.h"

#include "DomeMediaController.h"
#include "SpoutDomeReceiver.h"

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GenericPlatform/GenericApplication.h"
#include "GenericPlatform/GenericPlatformMisc.h"
#include "GenericPlatform/GenericWindow.h"
#include "Kismet/GameplayStatics.h"
#include "MediaPlayer.h"
#include "Engine/TextureRenderTarget2D.h"
#include "HAL/FileManager.h"
#include "ImageUtils.h"
#include "RenderingThread.h"
#include "Slate/WidgetRenderer.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SComboBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Input/SSpinBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SExpandableArea.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SWeakWidget.h"
#include "Widgets/SWindow.h"
#include "Widgets/Text/STextBlock.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <commdlg.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

#define LOCTEXT_NAMESPACE "DomoMenu"

namespace
{
	FSlateFontInfo Letra(int32 Tamano = 12)
	{
		return FCoreStyle::GetDefaultFontStyle("Regular", Tamano);
	}

	FSlateFontInfo LetraNegrita(int32 Tamano = 12)
	{
		return FCoreStyle::GetDefaultFontStyle("Bold", Tamano);
	}

	TSharedPtr<FString> Opcion(const TCHAR* Texto)
	{
		return MakeShared<FString>(Texto);
	}

	FText T(const FString& S)
	{
		return FText::FromString(S);
	}

	/** Dialogo de Windows para elegir uno o varios videos. Devuelve las rutas completas. */
	bool DialogoAbrirVideos(const FString& CarpetaInicial, TArray<FString>& Salida)
	{
#if PLATFORM_WINDOWS
		TArray<TCHAR> Buffer;
		Buffer.SetNumZeroed(65536);

		HWND Dueno = nullptr;
		if (GEngine && GEngine->GameViewport)
		{
			const TSharedPtr<SWindow> Ventana = GEngine->GameViewport->GetWindow();
			if (Ventana.IsValid() && Ventana->GetNativeWindow().IsValid())
			{
				Dueno = static_cast<HWND>(Ventana->GetNativeWindow()->GetOSWindowHandle());
			}
		}

		FString Inicial = FPaths::ConvertRelativePathToFull(CarpetaInicial);
		FPaths::MakePlatformFilename(Inicial);

		static const TCHAR Filtro[] =
			TEXT("Videos\0*.mp4;*.mov;*.mkv;*.avi;*.m4v;*.wmv;*.webm\0Todos los archivos\0*.*\0\0");

		OPENFILENAMEW Ofn;
		FMemory::Memzero(Ofn);
		Ofn.lStructSize = sizeof(Ofn);
		Ofn.hwndOwner = Dueno;
		Ofn.lpstrFilter = Filtro;
		Ofn.lpstrFile = Buffer.GetData();
		Ofn.nMaxFile = Buffer.Num();
		Ofn.lpstrInitialDir = *Inicial;
		Ofn.lpstrTitle = TEXT("Elegir video(s) para la cupula");
		Ofn.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_ALLOWMULTISELECT | OFN_NOCHANGEDIR;

		if (!GetOpenFileNameW(&Ofn))
		{
			return false;
		}

		// Una sola seleccion: "ruta completa\0\0". Varias: "carpeta\0a\0b\0\0".
		const TCHAR* P = Buffer.GetData();
		const FString Primero(P);
		P += Primero.Len() + 1;
		if (*P == 0)
		{
			Salida.Add(Primero);
		}
		else
		{
			while (*P != 0)
			{
				const FString Nombre(P);
				Salida.Add(FPaths::Combine(Primero, Nombre));
				P += Nombre.Len() + 1;
			}
		}
		return Salida.Num() > 0;
#else
		return false;
#endif
	}

	FString TiempoTexto(double Segundos)
	{
		const int32 S = FMath::Max(0, FMath::FloorToInt(static_cast<float>(Segundos)));
		return FString::Printf(TEXT("%02d:%02d"), S / 60, S % 60);
	}
}

// -----------------------------------------------------------------------------

FDomeMenu::FDomeMenu(ADomeMediaController* InDuenio)
	: Duenio(InDuenio)
{
	OpcionesFuente = { Opcion(TEXT("Spout (TouchDesigner en vivo)")), Opcion(TEXT("Media (videos de la lista)")) };
	OpcionesFormato = {
		Opcion(TEXT("360 equirectangular")), Opcion(TEXT("Domemaster (fisheye 180)")), Opcion(TEXT("VR180 mono")),
		Opcion(TEXT("VR180 lado a lado")), Opcion(TEXT("Plano 16:9 en una pantalla")) };
	OpcionesLuces = { Opcion(TEXT("Automaticas (con la senal)")), Opcion(TEXT("Encendidas")), Opcion(TEXT("Apagadas")) };
	OpcionesModo = { Opcion(TEXT("Caminar (gravedad y colisiones)")), Opcion(TEXT("Volar (sin gravedad)")), Opcion(TEXT("Fantasma (atraviesa todo)")) };
	for (int32 i = 0; i < ADomeMediaController::NumeroDePlantillas(); ++i)
	{
		OpcionesPlantilla.Add(MakeShared<FString>(ADomeMediaController::EtiquetaDePlantilla(i)));
	}
	OpcionesForma = { Opcion(TEXT("Plana (gnomonica)")), Opcion(TEXT("Curva (angulos iguales)")), Opcion(TEXT("Banda (da la vuelta)")),
		Opcion(TEXT("Tunel (polar)")), Opcion(TEXT("Cilindro (pared)")) };
	OpcionesEspejo = { Opcion(TEXT("Sin espejo")), Opcion(TEXT("Horizontal")), Opcion(TEXT("Vertical")), Opcion(TEXT("Ambos")) };
	OpcionesBordes = { Opcion(TEXT("Los cuatro lados")), Opcion(TEXT("Solo los costados")), Opcion(TEXT("Solo arriba y abajo")) };
	OpcionesCalidad = { Opcion(TEXT("VR (liviana)")), Opcion(TEXT("Render (capturas, pesada)")) };
	OpcionesSala = { Opcion(TEXT("Sala domo 180 (planetario)")), Opcion(TEXT("Sala 90")), Opcion(TEXT("Sala 45")) };
	MapasDeSala = { TEXT("DomoVR"), TEXT("DomoVR_90"), TEXT("DomoVR_45") };
}

FDomeMenu::~FDomeMenu()
{
	if (bEnViewport && Raiz.IsValid() && GEngine && GEngine->GameViewport)
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(Raiz.ToSharedRef());
	}
	Raiz.Reset();
}

int32 FDomeMenu::IndiceSala() const
{
	const ADomeMediaController* C = Duenio.Get();
	if (!C)
	{
		return 0;
	}
	const FString Nivel = UGameplayStatics::GetCurrentLevelName(C, true);
	const int32 I = MapasDeSala.IndexOfByPredicate([&](const FString& M) { return M.Equals(Nivel, ESearchCase::IgnoreCase); });
	return I == INDEX_NONE ? 0 : I;
}

void FDomeMenu::RecogerVistas()
{
	Vistas.Reset();
	OpcionesVista.Reset();
	ADomeMediaController* C = Duenio.Get();
	if (!C || !C->GetWorld())
	{
		return;
	}
	static const FName EtiquetaVista(TEXT("domo_vista"));
	const FString Prefijo(TEXT("vista:"));
	TArray<AActor*> Actores;
	UGameplayStatics::GetAllActorsWithTag(C, EtiquetaVista, Actores);
	for (AActor* A : Actores)
	{
		for (const FName& Tag : A->Tags)
		{
			const FString S = Tag.ToString();
			if (S.StartsWith(Prefijo))
			{
				FVista V;
				V.Nombre = S.Mid(Prefijo.Len());
				V.Ubicacion = A->GetActorLocation();
				V.Rotacion = A->GetActorRotation();
				Vistas.Add(V);
				break;
			}
		}
	}
	Vistas.Sort([](const FVista& A, const FVista& B) { return A.Nombre < B.Nombre; });
	for (const FVista& V : Vistas)
	{
		OpcionesVista.Add(MakeShared<FString>(V.Nombre));
	}
}

void FDomeMenu::RefrescarListas()
{
	ADomeMediaController* C = Duenio.Get();
	if (!C)
	{
		return;
	}
	OpcionesCue.Reset();
	for (int32 i = 0; i < C->Cues.Num(); ++i)
	{
		OpcionesCue.Add(MakeShared<FString>(FString::Printf(TEXT("%d. %s"), i + 1, *C->Cues[i].Nombre)));
	}
	RecogerVistas();
	if (ComboCue.IsValid())
	{
		StaticCastSharedPtr<SComboBox<TSharedPtr<FString>>>(ComboCue)->RefreshOptions();
	}
	if (ComboVista.IsValid())
	{
		StaticCastSharedPtr<SComboBox<TSharedPtr<FString>>>(ComboVista)->RefreshOptions();
	}
}

// --- Piezas de interfaz -------------------------------------------------------

TSharedRef<SWidget> FDomeMenu::Combo(TArray<TSharedPtr<FString>>* Opciones, TFunction<int32()> IndiceActual,
	TFunction<void(int32)> AlElegir, TSharedPtr<SWidget>* Guardar)
{
	using FCombo = SComboBox<TSharedPtr<FString>>;
	TSharedPtr<FCombo> Caja;
	SAssignNew(Caja, FCombo)
		.OptionsSource(Opciones)
		.HasDownArrow(false)
		.OnGenerateWidget_Lambda([](TSharedPtr<FString> Item)
		{
			return SNew(STextBlock).Text(T(Item.IsValid() ? *Item : FString())).Font(Letra());
		})
		.OnSelectionChanged_Lambda([Opciones, AlElegir](TSharedPtr<FString> Item, ESelectInfo::Type Info)
		{
			if (Info != ESelectInfo::Direct && Item.IsValid())
			{
				const int32 I = Opciones->Find(Item);
				if (I != INDEX_NONE)
				{
					AlElegir(I);
				}
			}
		})
		[
			SNew(STextBlock)
			.Font(Letra())
			.Text_Lambda([Opciones, IndiceActual]()
			{
				const int32 I = IndiceActual();
				return T((Opciones->IsValidIndex(I) ? *(*Opciones)[I] : FString(TEXT("Elegir..."))) + TEXT("   v"));
			})
		];
	if (Guardar)
	{
		*Guardar = Caja;
	}
	return Caja.ToSharedRef();
}

TSharedRef<SWidget> FDomeMenu::Fila(const FText& Etiqueta, TSharedRef<SWidget> Contenido)
{
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 8, 0)
		[
			SNew(SBox).WidthOverride(215.f)
			[
				SNew(STextBlock).Text(Etiqueta).Font(Letra()).ColorAndOpacity(FLinearColor(0.75f, 0.8f, 0.9f))
			]
		]
		+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)
		[
			Contenido
		];
}

TSharedRef<SWidget> FDomeMenu::Deslizador(const FText& Etiqueta, FName Parametro, float Min, float Max, float Paso)
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	return Fila(Etiqueta,
		SNew(SSpinBox<float>)
		.Font(Letra())
		.MinValue(Min)
		.MaxValue(Max)
		.MinSliderValue(Min)
		.MaxSliderValue(Max)
		.Delta(Paso)
		.Value_Lambda([Deb, Parametro]() { return Deb.IsValid() ? Deb->GetParam(Parametro) : 0.f; })
		.OnValueChanged_Lambda([Deb, Parametro](float V) { if (Deb.IsValid()) { Deb->SetParam(Parametro, V); } })
	);
}

TSharedRef<SWidget> FDomeMenu::Boton(const FText& Texto, TFunction<void()> Accion, const FText& Ayuda)
{
	return SNew(SButton)
		.ToolTipText(Ayuda)
		.OnClicked_Lambda([Accion]() { Accion(); return FReply::Handled(); })
		[
			SNew(STextBlock).Text(Texto).Font(Letra()).Justification(ETextJustify::Center)
		];
}

TSharedRef<SWidget> FDomeMenu::Casilla(const FText& Texto, TFunction<bool()> Estado, TFunction<void(bool)> AlCambiar)
{
	return SNew(SCheckBox)
		.IsChecked_Lambda([Estado]() { return Estado() ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
		.OnCheckStateChanged_Lambda([AlCambiar](ECheckBoxState E) { AlCambiar(E == ECheckBoxState::Checked); })
		[
			SNew(STextBlock).Text(Texto).Font(Letra())
		];
}

// --- Secciones ------------------------------------------------------------------

TSharedRef<SWidget> FDomeMenu::Titulo()
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	FDomeMenu* Yo = this;
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)
			[
				SNew(STextBlock).Text(LOCTEXT("Titulo", "DOMO  -  control")).Font(LetraNegrita(16))
			]
			+ SHorizontalBox::Slot().AutoWidth().Padding(4, 0, 0, 0)
			[
				Boton(LOCTEXT("Ocultar", "Ocultar (F2)"), [Yo]() { Yo->Mostrar(false); })
			]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
		[
			SNew(STextBlock)
			.Font(Letra(11))
			.ColorAndOpacity(FLinearColor(0.55f, 0.9f, 1.f))
			.AutoWrapText(true)
			.Text_Lambda([Deb]()
			{
				if (!Deb.IsValid())
				{
					return FText::GetEmpty();
				}
				const ADomeMediaController& C = *Deb;
				FString Estado = C.Fuente == EDomeFuente::Media ? TEXT("Media") : TEXT("Spout");
				Estado += C.HaySenal() ? TEXT("  |  con senal") : TEXT("  |  sin senal");
				if (C.bNegro)
				{
					Estado += TEXT("  |  NEGRO");
				}
				if (!C.UltimoMensaje.IsEmpty())
				{
					Estado += TEXT("\n") + C.UltimoMensaje;
				}
				Estado += TEXT("\n") + C.DescribirUdp();
				return T(Estado);
			})
		];
}

TSharedRef<SWidget> FDomeMenu::SeccionVideo()
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	FDomeMenu* Yo = this;
	RefrescarListas();

	TSharedRef<SVerticalBox> Caja = SNew(SVerticalBox);

	Caja->AddSlot().AutoHeight().Padding(0, 2)
	[
		Fila(LOCTEXT("Fuente", "Fuente"),
			Combo(&OpcionesFuente,
				[Deb]() { return Deb.IsValid() && Deb->Fuente == EDomeFuente::Media ? 1 : 0; },
				[Deb](int32 I) { if (Deb.IsValid()) { Deb->SetFuente(I == 1 ? EDomeFuente::Media : EDomeFuente::Spout); } }))
	];

	Caja->AddSlot().AutoHeight().Padding(0, 2)
	[
		Fila(LOCTEXT("Sender", "Sender Spout"),
			SNew(SEditableTextBox)
			.Font(Letra())
			.HintText(LOCTEXT("SenderAy", "nombre que publica TouchDesigner"))
			.ToolTipText(LOCTEXT("SenderAy2", "Nombre del sender de Spout (Syphon Spout Out de TouchDesigner). Enter para aplicar."))
			.Text((Deb.IsValid() && Deb->SpoutReceiver) ? FText::FromName(Deb->SpoutReceiver->SpoutSenderName) : FText::GetEmpty())
			.OnTextCommitted_Lambda([Deb](const FText& Texto, ETextCommit::Type)
			{
				if (Deb.IsValid() && Deb->SpoutReceiver && !Texto.IsEmpty())
				{
					Deb->SpoutReceiver->SpoutSenderName = FName(*Texto.ToString());
				}
			}))
	];

	Caja->AddSlot().AutoHeight().Padding(0, 2)
	[
		Fila(LOCTEXT("Video", "Video"),
			Combo(&OpcionesCue,
				[Deb]() { return Deb.IsValid() ? Deb->CueActual : 0; },
				[Deb](int32 I)
				{
					if (Deb.IsValid())
					{
						if (Deb->Fuente != EDomeFuente::Media)
						{
							Deb->SetFuente(EDomeFuente::Media);
						}
						Deb->GoToCue(I);
					}
				},
				&ComboCue))
	];

	Caja->AddSlot().AutoHeight().Padding(0, 4)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().FillWidth(0.6f).Padding(2, 0)
		[ Boton(LOCTEXT("Anterior", "|<"), [Deb]() { if (Deb.IsValid()) { Deb->Prev(); } }, LOCTEXT("AnteriorAy", "Video anterior (flecha izquierda)")) ]
		+ SHorizontalBox::Slot().FillWidth(1.4f).Padding(2, 0)
		[ Boton(LOCTEXT("Pausa", "Play/Pausa"), [Deb]() { if (Deb.IsValid()) { Deb->TogglePause(); } }, LOCTEXT("PausaAy", "Espacio")) ]
		+ SHorizontalBox::Slot().FillWidth(1.2f).Padding(2, 0)
		[ Boton(LOCTEXT("Reiniciar", "Reiniciar"), [Deb]() { if (Deb.IsValid()) { Deb->Reiniciar(); } }, LOCTEXT("ReiniciarAy", "Vuelve al principio (Inicio)")) ]
		+ SHorizontalBox::Slot().FillWidth(0.6f).Padding(2, 0)
		[ Boton(LOCTEXT("Siguiente", ">|"), [Deb]() { if (Deb.IsValid()) { Deb->Next(); } }, LOCTEXT("SiguienteAy", "Video siguiente (flecha derecha)")) ]
	];

	// Barra de tiempo.
	Caja->AddSlot().AutoHeight().Padding(0, 2)
	[
		SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(SSlider)
			.Value_Lambda([Deb, Yo]()
			{
				if (Yo->bSeekPendiente)
				{
					return Yo->SeekPendiente;
				}
				if (Deb.IsValid() && Deb->MediaPlayer)
				{
					const double D = Deb->MediaPlayer->GetDuration().GetTotalSeconds();
					return D > 0.0 ? static_cast<float>(Deb->MediaPlayer->GetTime().GetTotalSeconds() / D) : 0.f;
				}
				return 0.f;
			})
			.OnValueChanged_Lambda([Yo](float V) { Yo->SeekPendiente = V; Yo->bSeekPendiente = true; })
			.OnMouseCaptureEnd_Lambda([Deb, Yo]()
			{
				if (Yo->bSeekPendiente && Deb.IsValid() && Deb->MediaPlayer)
				{
					const double D = Deb->MediaPlayer->GetDuration().GetTotalSeconds();
					if (D > 0.0)
					{
						Deb->MediaPlayer->Seek(FTimespan::FromSeconds(D * Yo->SeekPendiente));
					}
				}
				Yo->bSeekPendiente = false;
			})
		]
		+ SVerticalBox::Slot().AutoHeight()
		[
			SNew(STextBlock).Font(Letra(11)).ColorAndOpacity(FLinearColor(0.7f, 0.7f, 0.7f))
			.Text_Lambda([Deb]()
			{
				if (Deb.IsValid() && Deb->MediaPlayer && Deb->Fuente == EDomeFuente::Media)
				{
					return T(TiempoTexto(Deb->MediaPlayer->GetTime().GetTotalSeconds()) + TEXT(" / ")
						+ TiempoTexto(Deb->MediaPlayer->GetDuration().GetTotalSeconds()));
				}
				return FText::GetEmpty();
			})
		]
	];

	Caja->AddSlot().AutoHeight().Padding(0, 4)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)
		[
			Boton(LOCTEXT("Abrir", "Abrir video..."),
				[Deb, Yo]()
				{
					if (!Deb.IsValid())
					{
						return;
					}
					TArray<FString> Rutas;
					if (DialogoAbrirVideos(Deb->CarpetaVideos(), Rutas))
					{
						Deb->AgregarVideos(Rutas);
						Yo->RefrescarListas();
					}
				},
				LOCTEXT("AbrirAy", "Elige uno o varios videos de cualquier carpeta y los agrega a la lista"))
		]
		+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)
		[
			Boton(LOCTEXT("Carpeta", "Traer la carpeta"),
				[Deb, Yo]()
				{
					if (Deb.IsValid())
					{
						Deb->EscanearCarpeta();
						Yo->RefrescarListas();
					}
				},
				LOCTEXT("CarpetaAy", "Agrega los videos de la carpeta de la lista que aun no estan"))
		]
	];

	Caja->AddSlot().AutoHeight().Padding(0, 2)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)
		[
			Boton(LOCTEXT("Recargar", "Recargar lista"),
				[Deb, Yo]() { if (Deb.IsValid()) { Deb->RecargarPlaylist(); Yo->RefrescarListas(); } },
				LOCTEXT("RecargarAy", "Vuelve a leer playlist.json (descarta los cambios sin guardar)"))
		]
		+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)
		[
			Boton(LOCTEXT("Guardar", "Guardar lista"),
				[Deb]() { if (Deb.IsValid()) { Deb->GuardarPlaylist(); } },
				LOCTEXT("GuardarAy", "Escribe playlist.json con los videos y los ajustes de imagen de cada uno"))
		]
	];

	Caja->AddSlot().AutoHeight().Padding(0, 6, 0, 0)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 18, 0)
		[
			Casilla(LOCTEXT("Repetir", "Repetir"),
				[Deb]() { return Deb.IsValid() && Deb->Cues.IsValidIndex(Deb->CueActual) && Deb->Cues[Deb->CueActual].Loop; },
				[Deb](bool b) { if (Deb.IsValid()) { Deb->SetLoop(b); } })
		]
		+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 18, 0)
		[
			Casilla(LOCTEXT("Auto", "Pasar al siguiente"),
				[Deb]() { return Deb.IsValid() && Deb->bAutoAvanzar; },
				[Deb](bool b) { if (Deb.IsValid()) { Deb->bAutoAvanzar = b; } })
		]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			Casilla(LOCTEXT("Negro", "Negro"),
				[Deb]() { return Deb.IsValid() && Deb->bNegro; },
				[Deb](bool b) { if (Deb.IsValid()) { Deb->Blackout(b); } })
		]
	];

	return Caja;
}

TSharedRef<SWidget> FDomeMenu::SeccionImagen()
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Fila(LOCTEXT("Formato", "Formato"),
				Combo(&OpcionesFormato,
					[Deb]() { return Deb.IsValid() && Deb->Cues.IsValidIndex(Deb->CueActual) ? static_cast<int32>(Deb->Cues[Deb->CueActual].Formato) : 0; },
					[Deb](int32 I) { if (Deb.IsValid()) { Deb->SetParam(TEXT("Formato"), static_cast<float>(I)); } }))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Brillo", "Brillo"), TEXT("Brillo"), 0.f, 3.f, 0.05f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Volumen", "Volumen"), TEXT("Volumen"), 0.f, 2.f, 0.05f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Yaw", "Giro (Yaw)"), TEXT("Yaw"), -180.f, 180.f, 1.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Pitch", "Inclinar (Pitch)"), TEXT("Pitch"), -90.f, 90.f, 1.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Roll", "Rodar (Roll)"), TEXT("Roll"), -180.f, 180.f, 1.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Horizonte", "Horizonte"), TEXT("Horizonte"), 0.f, 80.f, 1.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Curva", "Curva"), TEXT("Curva"), 0.2f, 3.f, 0.05f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Fov", "FOV contenido"), TEXT("FovContenido"), 0.f, 240.f, 1.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 6, 0, 2)
		[
			SNew(STextBlock).Text(LOCTEXT("Mapping", "Mapping del domemaster")).Font(LetraNegrita(11)).ColorAndOpacity(FLinearColor(0.75f, 0.8f, 0.9f))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("CentroX", "Centro X"), TEXT("CentroX"), -0.5f, 0.5f, 0.005f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("CentroY", "Centro Y"), TEXT("CentroY"), -0.5f, 0.5f, 0.005f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Escala", "Escala"), TEXT("Escala"), 0.5f, 2.f, 0.01f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Rotar", "Rotar"), TEXT("Rotar"), -180.f, 180.f, 1.f) ];
}

TSharedRef<SWidget> FDomeMenu::SeccionPantalla()
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;

	auto Sub = [](const FText& Titulo, TSharedRef<SWidget> Cuerpo, bool bCerrada)
	{
		return SNew(SExpandableArea)
			.InitiallyCollapsed(bCerrada && !FParse::Param(FCommandLine::Get(), TEXT("DomoMenuTodo")))
			.AreaTitle(Titulo)
			.AreaTitleFont(LetraNegrita(11))
			.BodyContent()
			[
				SNew(SBox).Padding(4, 2)[ Cuerpo ]
			];
	};
	auto Bloque = [](std::initializer_list<TSharedRef<SWidget>> Hijos)
	{
		TSharedRef<SVerticalBox> V = SNew(SVerticalBox);
		for (const TSharedRef<SWidget>& H : Hijos)
		{
			V->AddSlot().AutoHeight().Padding(0, 2)[ H ];
		}
		return V;
	};
	auto BotonFila = [this, Deb](int32 Indice)
	{
		return SNew(SButton)
			.OnClicked_Lambda([Deb, Indice]()
			{
				if (Deb.IsValid()) { Deb->SetCampoPantalla(TEXT("Editada"), static_cast<float>(Indice + 1)); }
				return FReply::Handled();
			})
			[
				SNew(STextBlock).Font(Letra(11)).Justification(ETextJustify::Center)
				.Text_Lambda([Deb, Indice]()
				{
					if (!Deb.IsValid() || !Deb->Cues.IsValidIndex(Deb->CueActual) || Indice >= Deb->Cues[Deb->CueActual].Pantallas.Num())
					{
						return FText::GetEmpty();
					}
					return FText::FromString(FString::Printf(TEXT("%s%d"), Deb->PantallaEditada == Indice ? TEXT("> Pantalla ") : TEXT("Pantalla "), Indice + 1));
				})
			];
	};

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			SNew(STextBlock).AutoWrapText(true).Font(Letra(11)).ColorAndOpacity(FLinearColor(0.7f, 0.7f, 0.7f))
			.Text(LOCTEXT("PantallaAy", "Montajes de pantallas para video 16:9 (los mismos de TouchDesigner). Elegir uno pone el formato en Plano 16:9. Cada pantalla se ajusta abajo y todo se guarda con Guardar lista."))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Fila(LOCTEXT("Plantilla", "Montaje"),
				Combo(&OpcionesPlantilla,
					[Deb]() { return Deb.IsValid() ? Deb->IndiceDePlantillaActual() : 0; },
					[Deb](int32 I) { if (Deb.IsValid()) { Deb->AplicarPlantilla(ADomeMediaController::IdDePlantilla(I)); } }))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1.f).Padding(1, 0)[ BotonFila(0) ]
			+ SHorizontalBox::Slot().FillWidth(1.f).Padding(1, 0)[ BotonFila(1) ]
			+ SHorizontalBox::Slot().FillWidth(1.f).Padding(1, 0)[ BotonFila(2) ]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)[ Boton(LOCTEXT("AgregarP", "+ Agregar pantalla"), [Deb]() { if (Deb.IsValid()) { Deb->AgregarPantalla(); } }) ]
			+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)[ Boton(LOCTEXT("QuitarP", "- Quitar la elegida"), [Deb]() { if (Deb.IsValid()) { Deb->QuitarPantalla(); } }) ]
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
		[
			Sub(LOCTEXT("SubForma", "Forma y tamano de la pantalla"),
				Bloque({
					Casilla(LOCTEXT("Encendida", "Encendida"),
						[Deb]() { return Deb.IsValid() && Deb->GetCampoPantalla(TEXT("Encendida")) > 0.5f; },
						[Deb](bool b) { if (Deb.IsValid()) { Deb->SetCampoPantalla(TEXT("Encendida"), b ? 1.f : 0.f); } }),
					Fila(LOCTEXT("Forma", "Forma"),
						Combo(&OpcionesForma,
							[Deb]() { return Deb.IsValid() ? FMath::RoundToInt(Deb->GetCampoPantalla(TEXT("Forma"))) : 0; },
							[Deb](int32 I) { if (Deb.IsValid()) { Deb->SetCampoPantalla(TEXT("Forma"), static_cast<float>(I)); } })),
					Deslizador(LOCTEXT("PYaw", "Azimut (grados)"), TEXT("S_Yaw"), -180.f, 180.f, 1.f),
					Deslizador(LOCTEXT("PElev", "Elevacion (grados)"), TEXT("S_Elevacion"), 0.f, 90.f, 1.f),
					Deslizador(LOCTEXT("PRoll", "Rodar (grados)"), TEXT("S_Roll"), -180.f, 180.f, 1.f),
					Deslizador(LOCTEXT("PAncho", "Ancho (grados)"), TEXT("S_Ancho"), 1.f, 360.f, 1.f),
					Deslizador(LOCTEXT("PAlto", "Alto (grados)"), TEXT("S_Alto"), 1.f, 180.f, 1.f),
					Deslizador(LOCTEXT("POpac", "Opacidad"), TEXT("S_Opacidad"), 0.f, 1.f, 0.01f),
					Deslizador(LOCTEXT("PBorde", "Borde suave"), TEXT("S_Borde"), 0.f, 0.5f, 0.005f) }),
				false)
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Sub(LOCTEXT("SubCopias", "Copias en anillo"),
				Bloque({
					Deslizador(LOCTEXT("PCopias", "Copias"), TEXT("S_Copias"), 1.f, 12.f, 1.f),
					Deslizador(LOCTEXT("PArco", "Arco que ocupan (grados)"), TEXT("S_Arco"), 10.f, 360.f, 1.f),
					Deslizador(LOCTEXT("PSolape", "Solape entre copias (grados)"), TEXT("S_Solape"), 0.f, 40.f, 0.5f),
					Casilla(LOCTEXT("PAlter", "Espejar de a una copia"),
						[Deb]() { return Deb.IsValid() && Deb->GetCampoPantalla(TEXT("EspejoAlterno")) > 0.5f; },
						[Deb](bool b) { if (Deb.IsValid()) { Deb->SetCampoPantalla(TEXT("EspejoAlterno"), b ? 1.f : 0.f); } }),
					Deslizador(LOCTEXT("PCorr", "Corrimiento del recorte por copia"), TEXT("S_Corrimiento"), 0.f, 1.f, 0.01f),
					Deslizador(LOCTEXT("PRep", "Repeticiones dentro (banda, tunel, cilindro)"), TEXT("S_Repeticion"), 1.f, 12.f, 0.5f) }),
				true)
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Sub(LOCTEXT("SubRecorte", "Recorte, espejo y bordes"),
				Bloque({
					Deslizador(LOCTEXT("PCropX", "Recorte: x"), TEXT("S_CropX"), -0.2f, 1.f, 0.01f),
					Deslizador(LOCTEXT("PCropY", "Recorte: y"), TEXT("S_CropY"), -0.2f, 1.f, 0.01f),
					Deslizador(LOCTEXT("PCropW", "Recorte: ancho"), TEXT("S_CropW"), 0.02f, 1.f, 0.01f),
					Deslizador(LOCTEXT("PCropH", "Recorte: alto"), TEXT("S_CropH"), 0.02f, 1.f, 0.01f),
					Fila(LOCTEXT("PEspejo", "Espejo"),
						Combo(&OpcionesEspejo,
							[Deb]() { return Deb.IsValid() ? FMath::RoundToInt(Deb->GetCampoPantalla(TEXT("Espejo"))) : 0; },
							[Deb](int32 I) { if (Deb.IsValid()) { Deb->SetCampoPantalla(TEXT("Espejo"), static_cast<float>(I)); } })),
					Fila(LOCTEXT("PBordes", "Bordes suaves"),
						Combo(&OpcionesBordes,
							[Deb]() { return Deb.IsValid() ? FMath::RoundToInt(Deb->GetCampoPantalla(TEXT("Bordes"))) : 0; },
							[Deb](int32 I) { if (Deb.IsValid()) { Deb->SetCampoPantalla(TEXT("Bordes"), static_cast<float>(I)); } })) }),
				true)
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Sub(LOCTEXT("SubAnim", "Movimiento del montaje"),
				Bloque({
					Deslizador(LOCTEXT("PGiroTodas", "Girar todo el montaje (grados)"), TEXT("S_GiroTodas"), -180.f, 180.f, 1.f),
					Deslizador(LOCTEXT("PVelGiro", "Giro continuo (grados/s)"), TEXT("S_VelGiro"), -90.f, 90.f, 0.5f),
					Deslizador(LOCTEXT("PVelRec", "Recorrido continuo (vueltas/s)"), TEXT("S_VelRecorrido"), -1.f, 1.f, 0.01f),
					Deslizador(LOCTEXT("PFacRec", "Esta pantalla: sigue el recorrido"), TEXT("S_Recorrido"), -3.f, 3.f, 0.05f),
					Deslizador(LOCTEXT("PFacGiro", "Esta pantalla: sigue el giro"), TEXT("S_Giro"), -3.f, 3.f, 0.05f) }),
				true)
		];
}

TSharedRef<SWidget> FDomeMenu::SeccionSalaYLuces()
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	FDomeMenu* Yo = this;
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Fila(LOCTEXT("Luces", "Luces de la sala"),
				Combo(&OpcionesLuces,
					[Deb]()
					{
						if (!Deb.IsValid()) { return 0; }
						return Deb->bLucesAutomaticas ? 0 : (Deb->bLucesEncendidas ? 1 : 2);
					},
					[Deb](int32 I)
					{
						if (!Deb.IsValid()) { return; }
						if (I == 0) { Deb->LucesAutomaticas(true); }
						else { Deb->SetLuces(I == 1); }
					}))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Velo", "Velo de la cupula con luces"), TEXT("Resplandor"), 0.f, 1.5f, 0.02f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Fila(LOCTEXT("Vista", "Punto de vista"),
				Combo(&OpcionesVista,
					[]() { return INDEX_NONE; },
					[Deb, Yo](int32 I)
					{
						if (!Deb.IsValid() || !Yo->Vistas.IsValidIndex(I)) { return; }
						Deb->IrAVista(Yo->Vistas[I].Ubicacion, Yo->Vistas[I].Rotacion, Yo->Vistas[I].Nombre);
					},
					&ComboVista))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Fila(LOCTEXT("Calidad", "Calidad"),
				Combo(&OpcionesCalidad,
					[Yo]() { return Yo->CalidadActual; },
					[Yo](int32 I)
					{
						Yo->CalidadActual = I;
						ADomeMediaController::AplicarPreset(I == 1 ? TEXT("Render") : TEXT("VR"));
					}))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Fila(LOCTEXT("Sala", "Sala"),
				Combo(&OpcionesSala,
					[Yo]() { return Yo->IndiceSala(); },
					[Deb, Yo](int32 I)
					{
						if (Deb.IsValid() && Yo->MapasDeSala.IsValidIndex(I) && I != Yo->IndiceSala())
						{
							UGameplayStatics::OpenLevel(Deb.Get(), FName(*Yo->MapasDeSala[I]));
						}
					}))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 8, 0, 0)
		[
			Boton(LOCTEXT("Salir", "Salir del programa"), []() { FPlatformMisc::RequestExit(false); })
		];
}

bool FDomeMenu::Fotografiar(const FString& Ruta, int32 Ancho, int32 Alto)
{
	if (!Panel.IsValid())
	{
		return false;
	}
	FWidgetRenderer* Dibujante = new FWidgetRenderer(true);
	UTextureRenderTarget2D* Textura = Dibujante->DrawWidget(Panel.ToSharedRef(), FVector2D(Ancho, Alto));
	FlushRenderingCommands();
	bool bOk = false;
	if (Textura)
	{
		if (FArchive* Ar = IFileManager::Get().CreateFileWriter(*Ruta))
		{
			bOk = FImageUtils::ExportRenderTarget2DAsPNG(Textura, *Ar);
			Ar->Close();
			delete Ar;
		}
	}
	delete Dibujante;
	return bOk;
}

TSharedRef<SWidget> FDomeMenu::BotonTecla(int32 Accion, int32 Ranura)
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	return SNew(SButton)
		.ToolTipText(LOCTEXT("TeclaAy", "Clic y luego pulsa la tecla nueva. Esc cancela; Supr la borra."))
		.OnClicked_Lambda([Deb, Accion, Ranura]()
		{
			if (Deb.IsValid()) { Deb->EsperarTecla(static_cast<EDomeAccion>(Accion), Ranura); }
			return FReply::Handled();
		})
		[
			SNew(STextBlock).Font(Letra(11)).Justification(ETextJustify::Center)
			.Text_Lambda([Deb, Accion, Ranura]()
			{
				if (!Deb.IsValid()) { return FText::GetEmpty(); }
				if (Deb->AccionEsperando == Accion && Deb->RanuraEsperando == Ranura)
				{
					return FText::FromString(TEXT("Pulsa una tecla..."));
				}
				return T(Deb->Controles.Texto(static_cast<EDomeAccion>(Accion), Ranura));
			})
		];
}

TSharedRef<SWidget> FDomeMenu::SeccionTeclas()
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	TSharedRef<SVerticalBox> Caja = SNew(SVerticalBox);
	Caja->AddSlot().AutoHeight().Padding(0, 2)
	[
		SNew(STextBlock).AutoWrapText(true).Font(Letra(11)).ColorAndOpacity(FLinearColor(0.7f, 0.7f, 0.7f))
		.Text(LOCTEXT("TeclasAy", "Cada accion tiene dos teclas. Se guardan solas en controles.json, junto a playlist.json. Los numeros 1 a 9 van siempre al video 1 a 9."))
	];
	for (int32 i = 0; i < static_cast<int32>(EDomeAccion::Cantidad); ++i)
	{
		Caja->AddSlot().AutoHeight().Padding(0, 1)
		[
			Fila(T(FDomeControles::Info(static_cast<EDomeAccion>(i)).Etiqueta),
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().FillWidth(1.f).Padding(0, 0, 2, 0)[ BotonTecla(i, 0) ]
				+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0, 0, 0)[ BotonTecla(i, 1) ])
		];
	}
	Caja->AddSlot().AutoHeight().Padding(0, 6, 0, 0)
	[
		Boton(LOCTEXT("RestTeclas", "Restablecer teclas"), [Deb]() { if (Deb.IsValid()) { Deb->RestablecerControles(true, false); } })
	];
	return Caja;
}

TSharedRef<SWidget> FDomeMenu::SeccionMovimiento()
{
	TWeakObjectPtr<ADomeMediaController> Deb = Duenio;
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)
		[
			Fila(LOCTEXT("Modo", "Modo"),
				Combo(&OpcionesModo,
					[Deb]() { return Deb.IsValid() ? static_cast<int32>(Deb->Controles.Modo) : 0; },
					[Deb](int32 I) { if (Deb.IsValid()) { Deb->PonerModoMovimiento(static_cast<EDomeModoMovimiento>(I)); } }))
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("VelCaminar", "Caminar (cm/s)"), TEXT("VelCaminar"), 50.f, 800.f, 10.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("VelVuelo", "Volar (cm/s)"), TEXT("VelVuelo"), 100.f, 3000.f, 10.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("MultCorrer", "Correr (multiplo)"), TEXT("MultCorrer"), 1.f, 6.f, 0.1f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("AlturaOjos", "Altura de ojos (cm)"), TEXT("AlturaOjos"), 60.f, 220.f, 1.f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Sensibilidad", "Sensibilidad del mouse"), TEXT("Sensibilidad"), 0.02f, 0.6f, 0.01f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Deslizador(LOCTEXT("Gravedad", "Gravedad"), TEXT("Gravedad"), 0.f, 3.f, 0.1f) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
		[
			Casilla(LOCTEXT("ClicDer", "Con el menu abierto, mirar solo con clic derecho"),
				[Deb]() { return Deb.IsValid() && Deb->Controles.bMirarSoloConClicDerecho; },
				[Deb](bool b) { if (Deb.IsValid()) { Deb->Controles.bMirarSoloConClicDerecho = b; Deb->AplicarMovimiento(); } })
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0, 4)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)
			[ Boton(LOCTEXT("Inicio", "Volver al inicio"), [Deb]() { if (Deb.IsValid()) { Deb->IrAlInicio(); } }) ]
			+ SHorizontalBox::Slot().FillWidth(1.f).Padding(2, 0)
			[ Boton(LOCTEXT("RestMov", "Restablecer movimiento"), [Deb]() { if (Deb.IsValid()) { Deb->RestablecerControles(false, true); } }) ]
		];
}

// --- Construccion y visibilidad -----------------------------------------------------

bool FDomeMenu::Construir()
{
	if (!GEngine || !GEngine->GameViewport || !Duenio.IsValid())
	{
		return false;
	}

	const bool bTodoAbierto = FParse::Param(FCommandLine::Get(), TEXT("DomoMenuTodo"));
	auto Seccion = [bTodoAbierto](const FText& Titulo, TSharedRef<SWidget> Cuerpo, bool bCerrada)
	{
		return SNew(SExpandableArea)
			.InitiallyCollapsed(bCerrada && !bTodoAbierto)
			.AreaTitle(Titulo)
			.AreaTitleFont(LetraNegrita(13))
			.BodyContent()
			[
				SNew(SBox).Padding(6, 4)[ Cuerpo ]
			];
	};

	const TSharedRef<SWidget> PanelNuevo =
		SNew(SBox)
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Fill)
		.Padding(FMargin(12.f))
		[
			SNew(SBox)
			.WidthOverride(600.f)
			[
				SNew(SBorder)
				.BorderImage(FCoreStyle::Get().GetBrush("GenericWhiteBox"))
				.BorderBackgroundColor(FLinearColor(0.02f, 0.03f, 0.05f, 0.82f))
				.Padding(10.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight()[ Titulo() ]
					+ SVerticalBox::Slot().FillHeight(1.f).Padding(0, 8, 0, 0)
					[
						SNew(SScrollBox)
						+ SScrollBox::Slot()
						[
							SNew(SVerticalBox)
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Seccion(LOCTEXT("SecVideo", "Fuente y video"), SeccionVideo(), false) ]
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Seccion(LOCTEXT("SecImagen", "Imagen en la cupula"), SeccionImagen(), true) ]
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Seccion(LOCTEXT("SecPantalla", "Pantallas 16:9 (montajes)"), SeccionPantalla(), true) ]
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Seccion(LOCTEXT("SecSala", "Sala, luces y vista"), SeccionSalaYLuces(), false) ]
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Seccion(LOCTEXT("SecMov", "Movimiento"), SeccionMovimiento(), true) ]
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 2)[ Seccion(LOCTEXT("SecTeclas", "Teclas"), SeccionTeclas(), true) ]
						]
					]
				]
			]
		];

	Panel = PanelNuevo;
	Raiz = SNew(SWeakWidget).PossiblyNullContent(PanelNuevo);
	Raiz->SetVisibility(EVisibility::Collapsed);
	GEngine->GameViewport->AddViewportWidgetContent(Raiz.ToSharedRef(), 50);
	bEnViewport = true;
	return true;
}

void FDomeMenu::Mostrar(bool bVer)
{
	bVisible = bVer;
	if (!Raiz.IsValid())
	{
		return;
	}
	Raiz->SetVisibility(bVer ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed);
	ADomeMediaController* C = Duenio.Get();
	APlayerController* PC = (C && C->GetWorld()) ? C->GetWorld()->GetFirstPlayerController() : nullptr;
	if (!PC)
	{
		return;
	}
	if (bVer)
	{
		RefrescarListas();
		PC->bShowMouseCursor = true;
		FInputModeGameAndUI Modo;
		Modo.SetHideCursorDuringCapture(false);
		Modo.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		PC->SetInputMode(Modo);
	}
	else
	{
		PC->bShowMouseCursor = false;
		PC->SetInputMode(FInputModeGameOnly());
	}
}

#undef LOCTEXT_NAMESPACE
