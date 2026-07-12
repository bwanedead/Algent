/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standard Next on Vercel: content pages are statically generated (SSG), but we keep the door
  // open for dynamic features later (search, charts, personalization) — so NOT `output: 'export'`.
  reactStrictMode: true,
};

export default nextConfig;
