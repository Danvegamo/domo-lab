/**
 * Implements D3D11-on-12 wrapping and scoped acquire/release helpers used by the Spout
 * sender path to copy from UE D3D12 textures into shared DX11 resources.
 */
#include "SpoutD3DUtils.h"
#include "SpoutD3DContext.h"

using Microsoft::WRL::ComPtr;

ComPtr<ID3D11Texture2D> WrapD3D12Resource(ID3D12Resource* Resource, D3D12_RESOURCE_STATES State)
{
	if (!Resource)
	{
		return nullptr;
	}

	FSpoutD3DContext& Context = FSpoutD3DContext::Get();
	ID3D11On12Device* D3D11On12 = Context.GetD3D11On12Device();
	if (!D3D11On12)
	{
		return nullptr;
	}

	D3D12_RESOURCE_DESC Desc = Resource->GetDesc();

	D3D11_RESOURCE_FLAGS Flags = {};
	Flags.BindFlags = D3D11_BIND_SHADER_RESOURCE;
	if (Desc.Flags & D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET)
	{
		Flags.BindFlags |= D3D11_BIND_RENDER_TARGET;
	}

	// Wrap the resource so the D3D11 immediate context can copy into/out of it.
	ComPtr<ID3D11Resource> WrappedResource;
	HRESULT hr = D3D11On12->CreateWrappedResource(
		Resource,
		&Flags,
		State,
		State,
		IID_PPV_ARGS(WrappedResource.GetAddressOf())
	);

	if (FAILED(hr))
	{
		return nullptr;
	}

	ComPtr<ID3D11Texture2D> Result;
	WrappedResource.As(&Result);
	return Result;
}

FScopedD3D11On12Acquire::FScopedD3D11On12Acquire(ID3D11Texture2D* InTexture)
{
	if (!InTexture)
	{
		return;
	}

	// Query for the ID3D11Resource interface required by Acquire/Release APIs.
	InTexture->QueryInterface(IID_PPV_ARGS(WrappedResource.GetAddressOf()));
	if (!WrappedResource)
	{
		return;
	}

	ID3D11On12Device* D3D11On12 = FSpoutD3DContext::Get().GetD3D11On12Device();
	if (D3D11On12)
	{
		// Acquire ensures correct resource state for D3D11 use on the D3D12 device.
		ID3D11Resource* RawWrapped = WrappedResource.Get();
		D3D11On12->AcquireWrappedResources(&RawWrapped, 1);
	}
}

FScopedD3D11On12Acquire::~FScopedD3D11On12Acquire()
{
	ID3D11On12Device* D3D11On12 = FSpoutD3DContext::Get().GetD3D11On12Device();
	if (D3D11On12 && WrappedResource)
	{
		// Release transitions the wrapped resource back to its original D3D12 state.
		ID3D11Resource* RawWrapped = WrappedResource.Get();
		D3D11On12->ReleaseWrappedResources(&RawWrapped, 1);
	}

	ID3D11DeviceContext* ImmediateContext = FSpoutD3DContext::Get().GetImmediateContext();
	if (ImmediateContext && WrappedResource)
	{
		// Flush required so D3D11 copies are visible to the D3D12 queue.
		ImmediateContext->Flush();
	}
}

bool FScopedD3D11On12Acquire::IsValid() const
{
	return WrappedResource != nullptr;
}
