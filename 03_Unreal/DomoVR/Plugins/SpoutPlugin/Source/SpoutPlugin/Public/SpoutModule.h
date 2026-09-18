/**
 * Declares the Spout plugin module interface and log category used by the runtime implementation.
 */
#pragma once

#include "Modules/ModuleManager.h"

// Global log category for the plugin to keep Spout/D3D diagnostics consistent.
DECLARE_LOG_CATEGORY_EXTERN(LogSpoutPlugin, Log, All);

class SPOUTPLUGIN_API FSpoutModule : public IModuleInterface
{
public:
	// Startup/shutdown are called on the game thread by the module manager.
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

	/**
	 * True once Spout.dll was explicitly loaded (via GetDllHandle) during
	 * StartupModule. Every caller that may end up touching a Spout.dll
	 * export (directly or through the delay-loaded SpoutDirectX/
	 * spoutSenderNames helpers, e.g. FSpoutD3DContext::Initialize) MUST
	 * check this first and bail out instead of calling in.
	 *
	 * Why this exists: PublicDelayLoadDLLs("Spout.dll") + the MSVC
	 * delay-load helper (delayhlp.cpp) resolve the DLL by its bare name
	 * using the normal Windows search order, which does NOT include this
	 * plugin's own Binaries/Win64 folder. If the DLL isn't already loaded
	 * in the process under that name, the first call into it raises
	 * ERROR_MOD_NOT_FOUND (0xC06D007E) as a raw structured exception --
	 * NOT a C++ exception -- which an ordinary catch(...) will not stop,
	 * so it takes the whole editor process down. Loading the DLL up front
	 * from its known absolute path (this module) makes the name resolve
	 * to the already-loaded module, so the delay-load helper never needs
	 * to search for it. This flag is the fallback for when even that
	 * explicit load fails.
	 */
	static bool IsSpoutRuntimeAvailable();

private:
	// Handle to the explicitly-loaded Spout.dll; released in ShutdownModule.
	void* SpoutDllHandle = nullptr;

	static bool bSpoutRuntimeAvailable;
};
