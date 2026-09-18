/**
 * Declares D3D helper utilities for wrapping D3D12 resources and managing D3D11-on-12
 * acquire/release scopes used by sender/receiver interop.
 */
#pragma once

#include "CoreMinimal.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <d3d11.h>
#include <d3d12.h>
#include <wrl/client.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

class FScopedD3D11On12Acquire
{
public:
	// Acquires a wrapped D3D11 resource for CPU/GPU access through the D3D11-on-12 device.
	explicit FScopedD3D11On12Acquire(ID3D11Texture2D* InTexture);
	// Releases the wrapped resource and flushes the D3D11 context to submit pending work.
	~FScopedD3D11On12Acquire();

	bool IsValid() const;

private:
	// Kept to release the wrapped resource on scope exit.
	Microsoft::WRL::ComPtr<ID3D11Resource> WrappedResource;
};

// Wraps a D3D12 resource so it can be used by Spout's D3D11 path.
Microsoft::WRL::ComPtr<ID3D11Texture2D> WrapD3D12Resource(ID3D12Resource* Resource, D3D12_RESOURCE_STATES State);
