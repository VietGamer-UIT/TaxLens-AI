/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output enables Docker multi-stage optimized builds
  output: 'standalone',
  // Disable x-powered-by header for security
  poweredByHeader: false,
}

module.exports = nextConfig
