import { useState } from 'react';
import { Camera } from 'lucide-react';
import { api } from '../services/api';
import type { VisionAttachment } from '../types/api';

interface Props {
  incidentId: string;
  vision?: VisionAttachment | null;
}

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export const VisionEvidence: React.FC<Props> = ({ incidentId, vision }) => {
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setErrorMsg(null);
    try {
      const b64 = await toBase64(file);
      const up = await api.uploadImage(b64, file.name);
      await api.attachImage(incidentId, up.image_id);
      // the dashboard polls every 1.5 s — next poll renders the attachment
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'upload failed');
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  return (
    <div className="mt-3 border border-slate-700 rounded-lg p-3 bg-slate-900/60">
      <div className="flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold tracking-wider text-slate-400">
          <Camera className="w-3.5 h-3.5" /> VISION EVIDENCE
        </h4>
        <label className="cursor-pointer text-xs text-sky-400 hover:text-sky-300">
          {isUploading ? 'Analyzing…' : 'Upload image'}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={handleFile}
            disabled={isUploading}
          />
        </label>
      </div>
      {errorMsg && <p className="mt-2 text-xs text-red-400">{errorMsg}</p>}
      {vision ? (
        <div className="mt-2 space-y-1 text-xs text-slate-300">
          <p>
            scene <span className="text-slate-100">{vision.facts.scene}</span> · damage{' '}
            <span className="text-slate-100">{vision.facts.damage_severity}</span> ·
            confidence {vision.facts.confidence['scene'] ?? '—'}
          </p>
          <p className="text-slate-500">
            {vision.facts.model_id} @ {vision.facts.mode} ·{' '}
            {vision.facts.status === 'ok' ? 'OK' : vision.facts.status}
            {vision.facts.objects.length > 0 && <> · {vision.facts.objects.join(', ')}</>}
          </p>
          {vision.soft_findings.map((f) => (
            <p key={f.code} className="text-amber-400">⚠ {f.message}</p>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          No image attached. Upload a scene photo as extra evidence.
        </p>
      )}
    </div>
  );
};
