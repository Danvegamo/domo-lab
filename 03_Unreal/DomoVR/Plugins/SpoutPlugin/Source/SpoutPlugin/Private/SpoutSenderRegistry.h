/**
 * Declares the shared sender/receiver registry and state objects that track Spout handles,
 * textures, and cached wrappers across the plugin.
 */
#pragma once

#include "CoreMinimal.h"
#include "SpoutBPFunctionLibrary.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <d3d11.h>
#include <wrl/client.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

class FSpoutSharedSender
{
public:
	FSpoutSharedSender(FName InName, ESpoutType InType);
	~FSpoutSharedSender();

	// Releases shared handles and unregisters sender names when applicable.
	void ReleaseResources();

	// Spout sender/receiver identifier (shared across the registry).
	FName Name;
	uint32 Width = 0;
	uint32 Height = 0;
	// Distinguishes sender vs receiver ownership semantics.
	ESpoutType Type = ESpoutType::Sender;
	bool bRegistered = false;

	// Shared DX11 texture exposed to other Spout clients (senders only).
	Microsoft::WRL::ComPtr<ID3D11Texture2D> SharedTexture;
	HANDLE SharedHandle = nullptr;

	// CPU-readable staging texture for receiver readback.
	Microsoft::WRL::ComPtr<ID3D11Texture2D> StagingTexture;
	// Optional intermediate texture for sender-side gamma correction.
	Microsoft::WRL::ComPtr<ID3D11Texture2D> GammaTexture;
	Microsoft::WRL::ComPtr<ID3D11RenderTargetView> GammaRTV;

	// Cached D3D11 wrapper for a D3D12 resource.
	// - Sender role: wraps the source UE RHI texture (state = COPY_SOURCE).
	// - Receiver role: wraps the primary destination UE RHI texture (state = COPY_DEST).
	// The role is fixed per FSpoutSharedSender instance because the registry is keyed by (Name, Type).
	Microsoft::WRL::ComPtr<ID3D11Texture2D> CachedWrappedResource;
	void* CachedNativeResource = nullptr;

	// Receiver role only: wraps the optional secondary render-target destination (state = COPY_DEST).
	Microsoft::WRL::ComPtr<ID3D11Texture2D> CachedRTWrappedResource;
	void* CachedRTNativeResource = nullptr;

	// Protects SharedTexture/handle updates across game and render threads.
	FCriticalSection ResourceMutex;
};

class FSpoutSenderRegistry
{
public:
	// Global registry of sender/receiver shared state.
	static FSpoutSenderRegistry& Get();

	// Finds an existing entry keyed by (Name, Type) or creates a new one.
	// Keying on Type prevents a sender and receiver with the same FName from
	// sharing (and corrupting) the same FSpoutSharedSender instance.
	TSharedPtr<FSpoutSharedSender> FindOrAdd(const FName& Name, ESpoutType Type);
	TSharedPtr<FSpoutSharedSender> Find(const FName& Name, ESpoutType Type);
	void Remove(const FName& Name, ESpoutType Type);
	void Clear();

private:
	// Keyed by (Name, Type) so senders and receivers with the same FName coexist.
	TMap<TPair<FName, ESpoutType>, TSharedPtr<FSpoutSharedSender>> Senders;
	// Protects registry mutations across threads.
	FCriticalSection Mutex;
};
