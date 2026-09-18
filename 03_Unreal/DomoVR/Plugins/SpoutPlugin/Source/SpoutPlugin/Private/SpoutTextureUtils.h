/**
 * Declares small texture utility helpers for creating and managing transient textures
 * and render targets used by the Spout receiver and sender flows.
 */
#pragma once

#include "CoreMinimal.h"
#include "Engine/Texture2D.h"
#include "Engine/TextureRenderTarget2D.h"

namespace SpoutTextureUtils
{
	// Releases a transient texture and its render resource.
	void DestroyTexture(UTexture2D*& Texture);
	// Ensures a transient texture exists with the requested size/format.
	bool EnsureTransientTexture(UTexture2D*& Texture, int32 Width, int32 Height, EPixelFormat Format);
	// Creates a render target suitable for sending via Spout.
	UTextureRenderTarget2D* CreateRenderTarget2D(int32 Width, int32 Height, EPixelFormat Format, bool bForceLinearGamma);
}
