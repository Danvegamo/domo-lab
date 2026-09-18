/**
 * Implements texture utility helpers for transient texture lifetime and render target
 * creation used by Blueprint-facing Spout APIs.
 */
#include "SpoutTextureUtils.h"

#include "TextureResource.h"
#include "RenderResource.h"

namespace SpoutTextureUtils
{
	void DestroyTexture(UTexture2D*& Texture)
	{
		if (!Texture)
		{
			return;
		}

		// Transient textures are rooted to avoid GC while in use by the plugin.
		if (Texture->IsRooted())
		{
			Texture->RemoveFromRoot();
		}

		// Ensure the render resource is released before GC.
		// FTextureResource derives from FRenderResource, so no cast is required.
		if (FTextureResource* Resource = Texture->GetResource())
		{
			BeginReleaseResource(Resource);
		}

		Texture->MarkAsGarbage();
		Texture = nullptr;
	}

	bool EnsureTransientTexture(UTexture2D*& Texture, int32 Width, int32 Height, EPixelFormat Format)
	{
		if (Texture && Texture->GetSizeX() == Width && Texture->GetSizeY() == Height)
		{
			return false;
		}

		DestroyTexture(Texture);

		// Transient textures are created on the game thread and updated on the render thread.
		Texture = UTexture2D::CreateTransient(Width, Height, Format);
		if (Texture)
		{
			Texture->AddToRoot();
			Texture->UpdateResource();
		}

		return true;
	}

	UTextureRenderTarget2D* CreateRenderTarget2D(int32 Width, int32 Height, EPixelFormat Format, bool bForceLinearGamma)
	{
		UTextureRenderTarget2D* RenderTarget = NewObject<UTextureRenderTarget2D>();
		// Root the render target to prevent GC while in use by the plugin.
		RenderTarget->AddToRoot();
		// Create a render target for GPU-side writes before sharing via Spout.
		RenderTarget->InitCustomFormat(Width, Height, Format, bForceLinearGamma);
		RenderTarget->AddressX = TextureAddress::TA_Wrap;
		RenderTarget->AddressY = TextureAddress::TA_Wrap;
		RenderTarget->UpdateResource();
		return RenderTarget;
	}
}
