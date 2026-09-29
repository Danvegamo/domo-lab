#include "DomeControles.h"

#include "Dom/JsonObject.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
	const FDomeAccionInfo& Tabla(int32 I)
	{
		// El orden es el de EDomeAccion.
		static const FDomeAccionInfo T[] = {
			{ TEXT("adelante"), TEXT("Adelante"), EKeys::W, EKeys::Invalid },
			{ TEXT("atras"), TEXT("Atras"), EKeys::S, EKeys::Invalid },
			{ TEXT("izquierda"), TEXT("Izquierda"), EKeys::A, EKeys::Invalid },
			{ TEXT("derecha"), TEXT("Derecha"), EKeys::D, EKeys::Invalid },
			{ TEXT("subir"), TEXT("Subir (vuelo)"), EKeys::E, EKeys::Invalid },
			{ TEXT("bajar"), TEXT("Bajar (vuelo)"), EKeys::Q, EKeys::Invalid },
			{ TEXT("correr"), TEXT("Correr"), EKeys::LeftShift, EKeys::Invalid },
			{ TEXT("cambiar_modo"), TEXT("Caminar / Volar / Fantasma"), EKeys::F, EKeys::Invalid },
			{ TEXT("siguiente"), TEXT("Siguiente video"), EKeys::Right, EKeys::PageDown },
			{ TEXT("anterior"), TEXT("Video anterior"), EKeys::Left, EKeys::PageUp },
			{ TEXT("negro"), TEXT("Negro"), EKeys::B, EKeys::Period },
			{ TEXT("pausa"), TEXT("Play / Pausa"), EKeys::SpaceBar, EKeys::Invalid },
			{ TEXT("reiniciar"), TEXT("Reiniciar video"), EKeys::Home, EKeys::Invalid },
			{ TEXT("fuente"), TEXT("Spout / Media"), EKeys::F3, EKeys::Invalid },
			{ TEXT("menu"), TEXT("Mostrar u ocultar el menu"), EKeys::F2, EKeys::M },
			{ TEXT("ayuda"), TEXT("Ayuda"), EKeys::F1, EKeys::Invalid },
		};
		static_assert(UE_ARRAY_COUNT(T) == static_cast<int32>(EDomeAccion::Cantidad), "tabla de acciones");
		return T[I];
	}
}

FDomeControles::FDomeControles()
{
	RestablecerTeclas();
}

const FDomeAccionInfo& FDomeControles::Info(EDomeAccion Accion)
{
	return Tabla(static_cast<int32>(Accion));
}

void FDomeControles::RestablecerTeclas()
{
	for (int32 i = 0; i < static_cast<int32>(EDomeAccion::Cantidad); ++i)
	{
		Teclas[i][0] = Tabla(i).PorDefectoA;
		Teclas[i][1] = Tabla(i).PorDefectoB;
	}
}

void FDomeControles::RestablecerMovimiento()
{
	Modo = EDomeModoMovimiento::Caminar;
	VelocidadCaminar = 250.f;
	VelocidadVuelo = 700.f;
	MultiplicadorCorrer = 2.5f;
	AlturaOjos = 160.f;
	Sensibilidad = 0.12f;
	Gravedad = 1.f;
	bMirarSoloConClicDerecho = true;
}

void FDomeControles::PonerTecla(EDomeAccion Accion, int32 Ranura, const FKey& Tecla)
{
	if (Ranura < 0 || Ranura > 1)
	{
		return;
	}
	Teclas[static_cast<int32>(Accion)][Ranura] = Tecla;
}

bool FDomeControles::Apretada(EDomeAccion Accion, const APlayerController* PC) const
{
	if (!PC)
	{
		return false;
	}
	for (int32 r = 0; r < 2; ++r)
	{
		const FKey& K = Teclas[static_cast<int32>(Accion)][r];
		if (K.IsValid() && PC->IsInputKeyDown(K))
		{
			return true;
		}
	}
	return false;
}

bool FDomeControles::RecienApretada(EDomeAccion Accion, const APlayerController* PC) const
{
	if (!PC)
	{
		return false;
	}
	for (int32 r = 0; r < 2; ++r)
	{
		const FKey& K = Teclas[static_cast<int32>(Accion)][r];
		if (K.IsValid() && PC->WasInputKeyJustPressed(K))
		{
			return true;
		}
	}
	return false;
}

FString FDomeControles::Texto(EDomeAccion Accion, int32 Ranura) const
{
	const FKey& K = Teclas[static_cast<int32>(Accion)][Ranura];
	return K.IsValid() ? K.GetDisplayName().ToString() : FString(TEXT("-"));
}

bool FDomeControles::Cargar(const FString& Ruta)
{
	FString Texto;
	if (!FFileHelper::LoadFileToString(Texto, *Ruta))
	{
		return false;
	}
	TSharedPtr<FJsonObject> Raiz;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Texto), Raiz) || !Raiz.IsValid())
	{
		return false;
	}
	const TSharedPtr<FJsonObject>* Teclado = nullptr;
	if (Raiz->TryGetObjectField(TEXT("teclas"), Teclado) && Teclado)
	{
		for (int32 i = 0; i < static_cast<int32>(EDomeAccion::Cantidad); ++i)
		{
			const TArray<TSharedPtr<FJsonValue>>* Lista = nullptr;
			if ((*Teclado)->TryGetArrayField(Tabla(i).Id, Lista) && Lista)
			{
				for (int32 r = 0; r < 2; ++r)
				{
					FString Nombre;
					Teclas[i][r] = (Lista->IsValidIndex(r) && (*Lista)[r]->TryGetString(Nombre) && !Nombre.IsEmpty())
						? FKey(*Nombre) : FKey();
				}
			}
		}
	}
	const TSharedPtr<FJsonObject>* Mov = nullptr;
	if (Raiz->TryGetObjectField(TEXT("movimiento"), Mov) && Mov)
	{
		double V = 0.0;
		FString Modo_;
		if ((*Mov)->TryGetStringField(TEXT("modo"), Modo_))
		{
			Modo = Modo_ == TEXT("volar") ? EDomeModoMovimiento::Volar
				: Modo_ == TEXT("fantasma") ? EDomeModoMovimiento::Fantasma : EDomeModoMovimiento::Caminar;
		}
		if ((*Mov)->TryGetNumberField(TEXT("velocidadCaminar"), V)) { VelocidadCaminar = static_cast<float>(V); }
		if ((*Mov)->TryGetNumberField(TEXT("velocidadVuelo"), V)) { VelocidadVuelo = static_cast<float>(V); }
		if ((*Mov)->TryGetNumberField(TEXT("multiplicadorCorrer"), V)) { MultiplicadorCorrer = static_cast<float>(V); }
		if ((*Mov)->TryGetNumberField(TEXT("alturaOjos"), V)) { AlturaOjos = static_cast<float>(V); }
		if ((*Mov)->TryGetNumberField(TEXT("sensibilidad"), V)) { Sensibilidad = static_cast<float>(V); }
		if ((*Mov)->TryGetNumberField(TEXT("gravedad"), V)) { Gravedad = static_cast<float>(V); }
		(*Mov)->TryGetBoolField(TEXT("mirarSoloConClicDerecho"), bMirarSoloConClicDerecho);
	}
	return true;
}

bool FDomeControles::Guardar(const FString& Ruta) const
{
	const TSharedRef<FJsonObject> Teclado = MakeShared<FJsonObject>();
	for (int32 i = 0; i < static_cast<int32>(EDomeAccion::Cantidad); ++i)
	{
		TArray<TSharedPtr<FJsonValue>> Lista;
		for (int32 r = 0; r < 2; ++r)
		{
			Lista.Add(MakeShared<FJsonValueString>(Teclas[i][r].IsValid() ? Teclas[i][r].ToString() : FString()));
		}
		Teclado->SetArrayField(Tabla(i).Id, Lista);
	}
	const TSharedRef<FJsonObject> Mov = MakeShared<FJsonObject>();
	Mov->SetStringField(TEXT("modo"), Modo == EDomeModoMovimiento::Volar ? TEXT("volar")
		: Modo == EDomeModoMovimiento::Fantasma ? TEXT("fantasma") : TEXT("caminar"));
	Mov->SetNumberField(TEXT("velocidadCaminar"), VelocidadCaminar);
	Mov->SetNumberField(TEXT("velocidadVuelo"), VelocidadVuelo);
	Mov->SetNumberField(TEXT("multiplicadorCorrer"), MultiplicadorCorrer);
	Mov->SetNumberField(TEXT("alturaOjos"), AlturaOjos);
	Mov->SetNumberField(TEXT("sensibilidad"), Sensibilidad);
	Mov->SetNumberField(TEXT("gravedad"), Gravedad);
	Mov->SetBoolField(TEXT("mirarSoloConClicDerecho"), bMirarSoloConClicDerecho);

	const TSharedRef<FJsonObject> Raiz = MakeShared<FJsonObject>();
	Raiz->SetObjectField(TEXT("teclas"), Teclado);
	Raiz->SetObjectField(TEXT("movimiento"), Mov);

	FString Texto;
	const TSharedRef<TJsonWriter<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>> Escritor =
		TJsonWriterFactory<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>::Create(&Texto);
	if (!FJsonSerializer::Serialize(Raiz, Escritor))
	{
		return false;
	}
	Escritor->Close();
	return FFileHelper::SaveStringToFile(Texto, *Ruta, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}
