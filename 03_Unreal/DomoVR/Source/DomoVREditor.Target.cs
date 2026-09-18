using UnrealBuildTool;
using System.Collections.Generic;

public class DomoVREditorTarget : TargetRules
{
	public DomoVREditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("DomoVR");
	}
}
