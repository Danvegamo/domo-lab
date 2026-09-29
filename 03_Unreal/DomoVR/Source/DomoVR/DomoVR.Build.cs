using UnrealBuildTool;

public class DomoVR : ModuleRules
{
	public DomoVR(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		// El modulo empezo vacio (solo para poder compilar el plugin
		// SpoutPlugin en un proyecto que de otro modo seria puro Blueprint).
		// Ahora tiene una sola clase, ASpoutDomeReceiver: el puente Spout se
		// resolvio en C++ en vez de Blueprint porque el usuario no queria
		// cablear nodos a mano, y porque hacerlo en Blueprint tiene un bug
		// real (ver ASpoutDomeReceiver.h) -- el resto del proyecto sigue
		// siendo Blueprint.
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore" });

		// SpoutPlugin: para USpoutBPFunctionLibrary::SpoutReceiver.
		PrivateDependencyModuleNames.AddRange(new string[] { "SpoutPlugin" });

		// ADomeMediaController: reproductor de video de la cupula sin
		// TouchDesigner (Media Framework, playlist en JSON, audio del video).
		PrivateDependencyModuleNames.AddRange(new string[] { "MediaAssets", "AudioMixer", "Json" });

		// DomeMenu: menu en pantalla en Slate (desplegables, deslizadores, botones)
		// y dialogo de Windows para abrir videos (comdlg32).
		PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore", "ApplicationCore", "UMG", "RenderCore", "Sockets", "Networking", "RHI", "HeadMountedDisplay" });
		if (Target.Platform == UnrealTargetPlatform.Win64)
		{
			PublicSystemLibraries.Add("comdlg32.lib");
		}
	}
}
