/**
 * Wires the module lifecycle to Spout resource startup/shutdown, delegating teardown to
 * the Blueprint function library's global shutdown path.
 */
#include "SpoutModule.h"
#include "SpoutBPFunctionLibrary.h"

#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"

DEFINE_LOG_CATEGORY(LogSpoutPlugin);

#define LOCTEXT_NAMESPACE "FSpoutModule"

bool FSpoutModule::bSpoutRuntimeAvailable = false;

#if PLATFORM_WINDOWS
namespace
{
	// Resolves the absolute path to Spout.dll the same way a precompiled
	// release or a source build would ship it: beside the plugin's own
	// module binary first, falling back to the vendored ThirdParty copy.
	// Shared by the diagnostic check and the explicit load below so both
	// always agree on where the DLL should be.
	FString FindSpoutDllPath()
	{
		const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("SpoutPlugin"));
		if (!Plugin.IsValid())
		{
			return FString();
		}

		const FString BaseDir = FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir());
		const FString BinariesDll = FPaths::Combine(BaseDir, TEXT("Binaries"), TEXT("Win64"), TEXT("Spout.dll"));
		if (IFileManager::Get().FileExists(*BinariesDll))
		{
			return BinariesDll;
		}

		const FString ThirdPartyDll = FPaths::Combine(BaseDir, TEXT("ThirdParty"), TEXT("Spout"), TEXT("lib"), TEXT("amd64"), TEXT("Spout.dll"));
		if (IFileManager::Get().FileExists(*ThirdPartyDll))
		{
			return ThirdPartyDll;
		}

		return FString();
	}

	// One-shot startup check: report whether Spout.dll is reachable so that
	// "module could not be loaded" failures are diagnosable from the log.
	// Runs only at module startup — never per frame.
	void VerifySpoutRuntime(const FString& ResolvedDllPath)
	{
		if (ResolvedDllPath.IsEmpty())
		{
			const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("SpoutPlugin"));
			if (!Plugin.IsValid())
			{
				UE_LOG(LogSpoutPlugin, Warning,
					TEXT("Could not locate the SpoutPlugin descriptor via IPluginManager; skipping Spout.dll diagnostics."));
				return;
			}
			const FString BaseDir = FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir());
			const FString BinariesDll = FPaths::Combine(BaseDir, TEXT("Binaries"), TEXT("Win64"), TEXT("Spout.dll"));
			const FString ThirdPartyDll = FPaths::Combine(BaseDir, TEXT("ThirdParty"), TEXT("Spout"), TEXT("lib"), TEXT("amd64"), TEXT("Spout.dll"));
			UE_LOG(LogSpoutPlugin, Error,
				TEXT("Spout.dll not found in either '%s' or '%s'. The module will fail to load. ")
				TEXT("Precompiled releases must ship Spout.dll in Binaries/Win64; source builds need it under ThirdParty/Spout/lib/amd64."),
				*BinariesDll, *ThirdPartyDll);
		}
		else
		{
			UE_LOG(LogSpoutPlugin, Verbose, TEXT("Spout.dll located at '%s'."), *ResolvedDllPath);
		}
	}
}
#endif // PLATFORM_WINDOWS

void FSpoutModule::StartupModule()
{
	UE_LOG(LogSpoutPlugin, Log, TEXT("Spout Plugin Loaded"));

#if PLATFORM_WINDOWS
	const FString DllPath = FindSpoutDllPath();
	VerifySpoutRuntime(DllPath);

	// Explicitly load Spout.dll from its known absolute path BEFORE any
	// code (SpoutDirectX, spoutSenderNames, ...) can trigger the MSVC
	// delay-load helper on it. See the comment on IsSpoutRuntimeAvailable()
	// in SpoutModule.h for why this is required, not optional: without it,
	// the delay-load helper searches for "Spout.dll" using the normal
	// Windows search order, which does not include this plugin's Binaries
	// folder, and fails with an unhandled ERROR_MOD_NOT_FOUND structured
	// exception the first time SpoutDirectX is touched -- observed in
	// practice as the editor crashing from
	// FSpoutD3DContext::Initialize() -> spoutDirectX::spoutDirectX()
	// whenever TouchDesigner (or any Spout sender) wasn't already running
	// with a matching, already-loaded Spout.dll elsewhere in the process.
	if (!DllPath.IsEmpty())
	{
		SpoutDllHandle = FPlatformProcess::GetDllHandle(*DllPath);
	}

	bSpoutRuntimeAvailable = (SpoutDllHandle != nullptr);
	if (!bSpoutRuntimeAvailable)
	{
		UE_LOG(LogSpoutPlugin, Error,
			TEXT("No se pudo cargar Spout.dll de forma explicita (ruta resuelta: '%s'). ")
			TEXT("Spout queda deshabilitado en esta sesion: SpoutSender/SpoutReceiver van a devolver ")
			TEXT("false sin tocar la biblioteca, en vez de arriesgar el crash de ERROR_MOD_NOT_FOUND ")
			TEXT("por carga diferida al primer uso real."),
			*DllPath);
	}
	else
	{
		UE_LOG(LogSpoutPlugin, Log, TEXT("Spout.dll cargada explicitamente desde '%s' (handle=%p)."), *DllPath, SpoutDllHandle);
	}
#else
	bSpoutRuntimeAvailable = false;
#endif
}

void FSpoutModule::ShutdownModule()
{
	// Ensure all DX/Spout resources are properly released before module teardown.
	USpoutBPFunctionLibrary::GlobalShutdown();

#if PLATFORM_WINDOWS
	if (SpoutDllHandle)
	{
		FPlatformProcess::FreeDllHandle(SpoutDllHandle);
		SpoutDllHandle = nullptr;
	}
#endif

	bSpoutRuntimeAvailable = false;

	UE_LOG(LogSpoutPlugin, Log, TEXT("Spout Plugin Unloaded"));
}

bool FSpoutModule::IsSpoutRuntimeAvailable()
{
	return bSpoutRuntimeAvailable;
}

#undef LOCTEXT_NAMESPACE
IMPLEMENT_MODULE(FSpoutModule, SpoutPlugin)
