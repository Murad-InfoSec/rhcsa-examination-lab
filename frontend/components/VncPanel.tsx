import React, { useEffect, useRef } from 'react';
// @ts-ignore — @novnc/novnc has no bundled type declarations
import RFB from '@novnc/novnc/lib/rfb';

interface VncPanelProps {
  wsPort: number;
  hostname: string;
  vmHostname: string;
}

const VncPanel: React.FC<VncPanelProps> = ({ wsPort, hostname, vmHostname }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const url = `ws://${hostname}:${wsPort}`;
    try {
      const rfb = new RFB(containerRef.current, url);
      rfb.scaleViewport = true;
      rfb.resizeSession = false;
      rfbRef.current = rfb;
    } catch (err) {
      console.error('noVNC RFB connect failed:', err);
    }

    return () => {
      if (rfbRef.current) {
        try { rfbRef.current.disconnect(); } catch {}
        rfbRef.current = null;
      }
    };
  }, [wsPort, hostname]);

  return (
    <div className="flex flex-col h-full bg-slate-900 overflow-hidden rounded-b-lg border-x border-b border-slate-700 shadow-2xl">
      {/* macOS-style titlebar */}
      <div className="bg-slate-800 px-4 py-1 flex items-center gap-2 border-b border-slate-700">
        <div className="w-3 h-3 rounded-full bg-red-500"></div>
        <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
        <div className="w-3 h-3 rounded-full bg-green-500"></div>
        <span className="text-xs text-slate-400 font-mono ml-2">VNC Console · {vmHostname}</span>
        <div className="ml-auto flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></div>
          <span className="text-[10px] text-green-500 font-bold uppercase">Live</span>
        </div>
      </div>
      <div ref={containerRef} className="flex-1 w-full h-full" />
    </div>
  );
};

export default VncPanel;
