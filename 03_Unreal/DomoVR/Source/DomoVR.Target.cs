using UnrealBuildTool;
using System.Collections.Generic;

public class DomoVRTarget : TargetRules
{
	public DomoVRTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("DomoVR");
	}
}
