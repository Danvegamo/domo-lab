// Teclas remapeables y ajustes de movimiento del ejecutable.
//
// Todas las acciones (moverse, cambiar de cue, negro, menu...) se leen por
// sondeo de teclas (APlayerController::IsInputKeyDown) contra esta tabla, en
// vez de estar cableadas con BindKey. Asi el menu puede cambiar una tecla en
// vivo y se guarda en controles.json, junto a playlist.json. Cada accion tiene
// dos teclas (A y B).

#pragma once

#include "CoreMinimal.h"
#include "InputCoreTypes.h"

class APlayerController;

/** Como se mueve el jugador. */
enum class EDomeModoMovimiento : uint8
{
	Caminar,
	Volar,
	Fantasma
};

enum class EDomeAccion : uint8
{
	Adelante,
	Atras,
	Izquierda,
	Derecha,
	Subir,
	Bajar,
	Correr,
	CambiarModo,
	Siguiente,
	Anterior,
	Negro,
	Pausa,
	Reiniciar,
	Fuente,
	Menu,
	Ayuda,
	Cantidad
};

struct FDomeAccionInfo
{
	const TCHAR* Id;         // clave en controles.json
	const TCHAR* Etiqueta;   // texto del menu
	FKey PorDefectoA;
	FKey PorDefectoB;
};

class FDomeControles
{
public:
	FDomeControles();

	static const FDomeAccionInfo& Info(EDomeAccion Accion);

	FKey Tecla(EDomeAccion Accion, int32 Ranura) const { return Teclas[static_cast<int32>(Accion)][Ranura]; }
	void PonerTecla(EDomeAccion Accion, int32 Ranura, const FKey& Tecla);

	bool Apretada(EDomeAccion Accion, const APlayerController* PC) const;
	bool RecienApretada(EDomeAccion Accion, const APlayerController* PC) const;

	/** Nombre corto de la tecla para el menu ("W", "Flecha izquierda", "-"). */
	FString Texto(EDomeAccion Accion, int32 Ranura) const;

	void RestablecerTeclas();
	void RestablecerMovimiento();

	bool Cargar(const FString& Ruta);
	bool Guardar(const FString& Ruta) const;

	// --- Movimiento (centimetros, segundos, grados) ---
	EDomeModoMovimiento Modo = EDomeModoMovimiento::Caminar;
	float VelocidadCaminar = 250.f;
	float VelocidadVuelo = 700.f;
	float MultiplicadorCorrer = 2.5f;
	float AlturaOjos = 160.f;
	/** Grados por unidad de mouse. */
	float Sensibilidad = 0.12f;
	float Gravedad = 1.f;
	/** Con el menu abierto el mouse solo gira la vista si se mantiene el clic derecho. */
	bool bMirarSoloConClicDerecho = true;

private:
	FKey Teclas[static_cast<int32>(EDomeAccion::Cantidad)][2];
};
