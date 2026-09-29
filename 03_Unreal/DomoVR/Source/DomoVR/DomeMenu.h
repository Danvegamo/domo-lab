// Menu en pantalla del ejecutable: controla la cupula sin TouchDesigner.
//
// FDomeMenu es un panel de Slate (desplegables, deslizadores, botones) que se
// agrega al viewport del juego y le habla a ADomeMediaController. No es un
// asset ni un Blueprint: se arma en codigo, asi que viaja dentro del build sin
// pasos manuales. F2 (o M) lo muestra y lo oculta; en el ejecutable arranca
// visible. Ver 04_Docs/06_Unreal_standalone.md, seccion "Menu en pantalla".

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SWidget.h"

class ADomeMediaController;
class SWidget;

class FDomeMenu : public TSharedFromThis<FDomeMenu>
{
public:
	explicit FDomeMenu(ADomeMediaController* InDuenio);
	~FDomeMenu();

	/** Arma el panel y lo agrega al viewport (oculto). Devuelve false si no hay viewport. */
	bool Construir();

	void Mostrar(bool bVer);
	void Alternar() { Mostrar(!bVisible); }
	bool EstaVisible() const { return bVisible; }

	/** Vuelve a leer la lista de cues y de puntos de vista (tras cargar o agregar videos). */
	void RefrescarListas();

	/** Dibuja el panel en un PNG (para verificar el menu sin ventana: domo.MenuFoto). */
	bool Fotografiar(const FString& Ruta, int32 Ancho, int32 Alto);

private:
	struct FVista
	{
		FString Nombre;
		FVector Ubicacion = FVector::ZeroVector;
		FRotator Rotacion = FRotator::ZeroRotator;
	};

	TWeakObjectPtr<ADomeMediaController> Duenio;
	TSharedPtr<SWidget> Raiz;
	TSharedPtr<SWidget> Panel;
	bool bVisible = false;
	bool bEnViewport = false;

	TArray<TSharedPtr<FString>> OpcionesFuente;
	TArray<TSharedPtr<FString>> OpcionesReproductor;
	TArray<TSharedPtr<FString>> OpcionesCue;
	TArray<TSharedPtr<FString>> OpcionesFormato;
	TArray<TSharedPtr<FString>> OpcionesLuces;
	TArray<TSharedPtr<FString>> OpcionesVista;
	TArray<TSharedPtr<FString>> OpcionesCalidad;
	TArray<TSharedPtr<FString>> OpcionesSala;
	TArray<TSharedPtr<FString>> OpcionesModo;
	TArray<TSharedPtr<FString>> OpcionesPlantilla;
	TArray<TSharedPtr<FString>> OpcionesForma;
	TArray<TSharedPtr<FString>> OpcionesEspejo;
	TArray<TSharedPtr<FString>> OpcionesBordes;
	TArray<FVista> Vistas;
	TArray<FString> MapasDeSala;

	// Los desplegables de listas que cambian se guardan para refrescarlos.
	TSharedPtr<SWidget> ComboCue;
	TSharedPtr<SWidget> ComboVista;

	int32 CalidadActual = 0;
	float SeekPendiente = 0.f;
	bool bSeekPendiente = false;

	void RecogerVistas();
	int32 IndiceSala() const;

	// Bloques de interfaz.
	TSharedRef<SWidget> Titulo();
	TSharedRef<SWidget> SeccionVideo();
	TSharedRef<SWidget> SeccionImagen();
	TSharedRef<SWidget> SeccionPantalla();
	TSharedRef<SWidget> SeccionSalaYLuces();
	TSharedRef<SWidget> SeccionMovimiento();
	TSharedRef<SWidget> SeccionTeclas();
	TSharedRef<SWidget> BotonTecla(int32 Accion, int32 Ranura);

	TSharedRef<SWidget> Combo(TArray<TSharedPtr<FString>>* Opciones, TFunction<int32()> IndiceActual,
		TFunction<void(int32)> AlElegir, TSharedPtr<SWidget>* Guardar = nullptr);
	TSharedRef<SWidget> Deslizador(const FText& Etiqueta, FName Parametro, float Min, float Max, float Paso);
	TSharedRef<SWidget> Boton(const FText& Texto, TFunction<void()> Accion, const FText& Ayuda = FText::GetEmpty());
	TSharedRef<SWidget> Casilla(const FText& Texto, TFunction<bool()> Estado, TFunction<void(bool)> AlCambiar);
	TSharedRef<SWidget> Fila(const FText& Etiqueta, TSharedRef<SWidget> Contenido);
};
