/**
 * Declares the sender API that bridges Blueprint requests to the render-thread Spout
 * publishing path implemented in SpoutSender.cpp.
 */
#pragma once

#include "CoreMinimal.h"
#include "SpoutBPFunctionLibrary.h"

class FSpoutSender
{
public:
	// Kicks a render-thread copy from an RHI texture to a shared Spout DX11 texture.
	static bool Send(FName SpoutName, ESpoutSendTextureFrom SendTextureFrom, UTextureRenderTarget2D* TextureRenderTarget2D);
	// Removes a sender from the registry and releases its shared handle.
	static void Close(FName SpoutName);
	// Removes viewport hooks used by the GameViewport sender path.
	static void Shutdown();
};
