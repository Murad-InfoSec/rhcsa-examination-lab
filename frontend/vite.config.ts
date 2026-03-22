import path from 'path';
import fs from 'fs';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Patch @novnc/novnc/lib/util/browser.js which contains a top-level await
// in a CommonJS module — invalid in Rollup's CJS wrapper. The await only
// enables optional WebCodecs H264 decode; removing it leaves the safe default (false).
const novncBrowserPatch = {
  name: 'patch-novnc-browser',
  load(id: string) {
    if (!id.startsWith('\0') && !id.includes('?') &&
        (id.includes('@novnc/novnc/lib/util/browser.js') || id.includes('@novnc/novnc\\lib\\util\\browser.js'))) {
      const src = fs.readFileSync(id, 'utf8');
      // Remove the top-level await assignment; initial value of false on line 91 is kept
      return src.replace(
        /exports\.supportsWebCodecsH264Decode\s*=\s*supportsWebCodecsH264Decode\s*=\s*await\s+[^;]+;/,
        '// top-level await removed by vite patch plugin (supportsWebCodecsH264Decode stays false)'
      );
    }
  },
};

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    return {
      root: __dirname,
      build: {
        outDir: path.resolve(__dirname, '../backend/frontend_dist'),
        emptyOutDir: true,
        target: 'esnext',
      },
      server: {
        port: 3000,
        host: '0.0.0.0',
        proxy: {
          '/api': 'http://localhost:5000',
          '/socket.io': {
            target: 'http://localhost:5000',
            ws: true,
          },
        },
      },
      plugins: [novncBrowserPatch, react()],
      define: {
        'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});
