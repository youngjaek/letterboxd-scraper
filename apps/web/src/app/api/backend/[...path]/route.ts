import { NextRequest } from "next/server";
import { serverApiBase } from "@/lib/api-base";

function normalizeBase(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function buildTargetUrl(pathSegments: string[] | undefined, search: string): string {
  const segments = pathSegments && pathSegments.length > 0 ? pathSegments.join("/") : "";
  const normalizedPath = segments ? `/${segments}` : "";
  const base = normalizeBase(serverApiBase);
  return `${base}${normalizedPath}${search ?? ""}`;
}

async function proxyRequest(request: NextRequest, context: { params: { path?: string[] } }) {
  const targetUrl = buildTargetUrl(context.params.path, request.nextUrl.search);
  const headers = new Headers(request.headers);
  headers.delete("host");
  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };
  if (!["GET", "HEAD"].includes(request.method.toUpperCase())) {
    const body = await request.arrayBuffer();
    init.body = body;
  }
  const upstream = await fetch(targetUrl, init);
  const responseHeaders = new Headers(upstream.headers);
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function PUT(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function PATCH(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function DELETE(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function OPTIONS(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}
