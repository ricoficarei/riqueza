import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { DragEvent, ReactNode } from 'react'
import { ArrowDownToLine, ArrowLeft, ArrowRight, AudioLines, Check, CheckCircle2, ChevronDown, ChevronRight, CircleAlert, CircleHelp, Clapperboard, Clock3, Film, FolderOpen, History, ImagePlus, Info, Layers3, LoaderCircle, LockKeyhole, LogOut, Maximize2, Play, Plus, RefreshCw, ScanFace, Settings2, ShieldCheck, Sparkles, Trash2, Upload, WandSparkles, X } from 'lucide-react'
import { api, assetUrl, isActive, isComplete, outputUrl, ApiError } from './api'
import type { Asset, Capabilities, GenerationSettings, Job, LocalEngineSettings } from './types'

const DEFAULT_SETTINGS: GenerationSettings = { model_version: 'v3', quality: 'standard', character_orientation: 'video', keep_original_sound: true, prompt: '', duration: 3, trim_start: 0, output_fps: 24 }
const STATUS_LABELS: Record<string, string> = { queued: 'Na fila', preparing: 'Preparando mídia', submitting: 'Enviando ao motor', running: 'Gerando vídeo', validating: 'Validando resultado', completed: 'Concluído', failed: 'Falhou', canceled: 'Cancelado', cancelled: 'Cancelado', blocked: 'Bloqueado' }
const dateFormat = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
function formatDate(value: string) { const d = new Date(value); return Number.isNaN(d.getTime()) ? value : dateFormat.format(d) }
function fileSize(bytes: number) { return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB` }
function errorMessage(error: unknown) { return error instanceof Error ? error.message : 'Ocorreu um erro inesperado. Tente novamente.' }
function downloadUrl(url: string) { return `${url}${url.includes('?') ? '&' : '?'}download=true` }

function ComparisonVideos({ job, result }: { job: Job; result: string }) {
  const referenceVideo = useRef<HTMLVideoElement>(null)
  const resultVideo = useRef<HTMLVideoElement>(null)
  const start = job.settings?.trim_start ?? 0
  const duration = job.settings?.duration ?? Infinity
  const sync = () => {
    const reference = referenceVideo.current
    const output = resultVideo.current
    if (!reference || !output || !reference.readyState) return
    const target = Math.min(start + output.currentTime, start + duration, reference.duration)
    if (Number.isFinite(target) && Math.abs(reference.currentTime - target) > 0.15) reference.currentTime = target
    if (output.paused || output.ended || output.currentTime >= duration) reference.pause()
    else void reference.play().catch(() => { /* The output controls remain usable when autoplay is restricted. */ })
  }
  return <div className="result-content comparison"><div className="comparison-item"><span>REFERÊNCIA · {start.toFixed(1)}s EM DIANTE</span><video ref={referenceVideo} muted playsInline preload="metadata" onLoadedMetadata={sync} src={`/api/assets/${encodeURIComponent(job.reference_id)}/file`} /></div><div className="comparison-item"><span>RESULTADO · CONTROLES SINCRONIZADOS</span><video ref={resultVideo} controls playsInline preload="metadata" onPlay={sync} onPause={sync} onTimeUpdate={sync} onSeeked={sync} src={result} /></div></div>
}

function JobDiagnostics({ job }: { job: Job }) {
  const report = job.quality_report
  const checks = Array.isArray(report?.checks) ? report.checks.filter((value): value is { name: string; status: string; message: string } => typeof value === 'object' && value !== null && typeof value.name === 'string' && typeof value.status === 'string' && typeof value.message === 'string') : []
  const limitation = typeof report?.limitation === 'string' ? report.limitation : null
  const labels: Record<string, string> = { video_decodable: 'Integridade do vídeo', brightness_continuity: 'Continuidade da luz', scene_continuity: 'Continuidade visual', sharpness: 'Nitidez medida', visual_metrics: 'Métricas visuais', identity_anatomy_and_consent: 'Revisão especializada' }
  return <section className="job-diagnostics" aria-label="Diagnóstico da geração"><details open={Boolean(report)}><summary><ShieldCheck size={15} /><span>Verificações e registro da geração</span><ChevronDown size={14} /></summary><div className="diagnostics-content">{checks.length > 0 && <div className="quality-checks"><h3>Verificações do vídeo</h3><ul>{checks.map((check, index) => <li key={`${check.name}-${index}`} className={`quality-check check-${check.status}`}><span>{check.status === 'passed' ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}</span><div><strong>{labels[check.name] ?? check.name}</strong><p>{check.message}</p></div><small>{check.status === 'passed' ? 'Verificado' : 'Revisar'}</small></li>)}</ul></div>}{limitation && <p className="diagnostics-limitation">{limitation}</p>}{!report && <p className="diagnostics-limitation">As verificações do vídeo aparecerão quando houver um resultado processado. Não há avaliação de identidade ou anatomia disponível.</p>}<div className="job-logs"><h3>Registro de processamento</h3>{job.logs?.length ? <ol>{job.logs.map((log, index) => <li key={`${log.time ?? ''}-${index}`}><time>{log.time ? formatDate(log.time) : '—'}</time><span>{log.message}</span></li>)}</ol> : <p>O servidor ainda não retornou registros para esta geração.</p>}</div></div></details></section>
}

function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={`brand ${compact ? 'brand-compact' : ''}`}><span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 40 40" fill="none"><path d="M5 29V11l8 8 7-12 7 12 8-8v18l-8-5-7 9-7-9-8 5Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /><path d="m13 19 7 6 7-6" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /></svg></span><span>MAYCOM CHEF<span className="brand-control">CONTROL<span className="brand-dot" aria-hidden="true">•</span></span></span></div>
}

function StatusPill({ job }: { job: Job }) { return <span className={`status-pill status-${job.status}`}>{isActive(job) ? <LoaderCircle size={12} className="spin" /> : isComplete(job) ? <Check size={12} /> : ['failed', 'blocked'].includes(job.status) ? <CircleAlert size={12} /> : <span className="status-dot" />}{STATUS_LABELS[job.status] ?? job.status}</span> }

function UploadCard({ role, asset, onUpload, onRemove, onReview, busy, videoCharacter }: { role: Asset['role']; asset: Asset | null; onUpload: (file: File, role: Asset['role']) => void; onRemove: () => void; onReview: (asset: Asset) => void; busy: boolean; videoCharacter: boolean }) {
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const id = useId()
  const isCharacter = role === 'character'
  const accept = isCharacter && videoCharacter ? 'image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm' : isCharacter ? 'image/jpeg,image/png,image/webp' : 'video/mp4,video/quicktime,video/webm'
  const handleDrop = (event: DragEvent) => { event.preventDefault(); setDragging(false); if (!busy && event.dataTransfer.files[0]) onUpload(event.dataTransfer.files[0], role) }
  return <section className="source-card">
    <div className="source-card-heading"><div className="step-title"><span className="step-number">{isCharacter ? '01' : '02'}</span><h2>{isCharacter ? 'Sua personagem' : 'Referência de movimento'}</h2></div><span className="small-label">{isCharacter ? 'IDENTIDADE' : 'MOVIMENTO'}</span></div>
    <input ref={input} id={id} className="sr-only" type="file" accept={accept} disabled={busy} onChange={event => { if (event.target.files?.[0]) onUpload(event.target.files[0], role); event.target.value = '' }} />
    <div className={`upload-zone ${dragging ? 'dragging' : ''} ${asset ? 'has-asset' : ''}`} onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={handleDrop}>
      {asset ? <><div className="uploaded-media">{asset.kind === 'video' ? <video src={assetUrl(asset)} controls preload="metadata" playsInline /> : <img src={assetUrl(asset)} alt={isCharacter ? 'Personagem selecionada para preservar a identidade' : 'Referência selecionada'} />}</div><button className="media-remove icon-button" title="Excluir arquivo enviado" aria-label="Excluir arquivo enviado" onClick={onRemove} disabled={busy}><X size={15} /></button><span className="asset-tag"><CheckCircle2 size={12} /> Arquivo enviado</span></> : <button className="upload-trigger" onClick={() => input.current?.click()} disabled={busy} aria-describedby={`${id}-description`}>
        <span className={`upload-icon ${isCharacter ? 'character-icon' : 'motion-icon'}`}>{busy ? <LoaderCircle size={26} className="spin" /> : isCharacter ? <ImagePlus size={27} strokeWidth={1.4} /> : <Clapperboard size={27} strokeWidth={1.4} />}</span>
        <span className="upload-title">{busy ? 'Preparando seu arquivo…' : isCharacter ? 'Adicione uma personagem' : 'Adicione um movimento'}</span>
        <span className="upload-description" id={`${id}-description`}>{isCharacter ? 'Uma imagem ou vídeo de uma pessoa adulta fictícia' : 'Um vídeo com a ação que deseja reproduzir'}</span>
        <span className="upload-choose"><Upload size={12} /> Escolher arquivo <span>ou arraste aqui</span></span>
        <span className="file-formats">{isCharacter ? `JPG, PNG, WEBP${videoCharacter ? ', MP4, MOV' : ''}` : 'MP4, MOV, WEBM · a partir de 3s'}</span>
      </button>}
    </div>
    {asset ? <div className="asset-details"><div><span className="asset-name" title={asset.filename}>{asset.filename}</span><span className="asset-metadata">{fileSize(asset.size)}{asset.width && asset.height ? ` · ${asset.width} × ${asset.height}` : ''}{asset.duration ? ` · ${asset.duration.toFixed(1)}s` : ''}</span></div><button className="icon-button" title="Trocar arquivo" aria-label="Trocar arquivo" onClick={() => input.current?.click()} disabled={busy}><RefreshCw size={14} /></button></div> : <p className="source-note"><Info size={12} /> {isCharacter ? 'Boa iluminação e corpo visível ajudam na consistência.' : 'Prefira uma pessoa, sem cortes ou obstruções.'}</p>}
    {asset && <div className="asset-review-row"><span className={`review-badge review-${asset.review_status}`}><ShieldCheck size={11} />{asset.review_status === 'approved' ? 'Aprovado' : asset.review_status === 'rejected' ? 'Rejeitado' : 'Revisão pendente'}</span><button className="text-button" onClick={() => onReview(asset)}>{asset.review_status === 'pending' ? 'Revisar arquivo' : 'Ver revisão'} <ChevronRight size={11} /></button></div>}
    {isCharacter && asset?.kind === 'video' && <p className="source-note amber-text"><Info size={12} /> O primeiro frame será usado como identidade.</p>}
  </section>
}

function EmptyPreview() { return <div className="empty-preview"><div className="preview-orbit orbit-outer" /><div className="preview-orbit orbit-inner" /><div className="preview-cross cross-one" /><div className="preview-cross cross-two" /><div className="empty-preview-icon"><WandSparkles size={34} strokeWidth={1.15} /></div><span className="eyebrow">SUA PRÓXIMA CRIAÇÃO</span><h3>Da referência<br /><span>ao seu universo.</span></h3><p>Envie a personagem e o movimento.<br />O resultado da geração aparecerá aqui.</p><div className="empty-preview-flow"><ScanFace size={15} /><span /><AudioLines size={15} /><span /><Film size={15} /></div></div> }

function DesktopEngineDialog({ onClose, onConfigured }: { onClose: () => void; onConfigured: () => Promise<void> }) {
  const [url, setUrl] = useState('http://127.0.0.1:8188')
  const [status, setStatus] = useState<LocalEngineSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    void api.localSettings().then(result => {
      if (active) { setStatus(result); setUrl(result.url) }
    }).catch(reason => { if (active) setError(errorMessage(reason)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  const save = async () => {
    if (busy) return
    setBusy(true); setError(null); setMessage(null)
    try {
      const result = await api.saveLocalSettings({ url: url.trim() })
      setStatus(result)
      await onConfigured()
      setMessage(result.ready ? 'Conexão e componentes encontrados. Comece com um trecho curto para testar sua placa de vídeo.' : 'Endereço salvo. Confira os requisitos abaixo antes de gerar.')
    } catch (reason) { setError(errorMessage(reason)) }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop engine-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}><form className="help-modal engine-modal" role="dialog" aria-modal="true" aria-labelledby="engine-title" onSubmit={event => { event.preventDefault(); void save() }}>
    <div className="modal-header"><span className="modal-icon"><WandSparkles size={22} /></span><button type="button" className="icon-button" aria-label="Fechar configuração do motor" disabled={busy} onClick={onClose}><X size={19} /></button></div>
    <span className="eyebrow">IA NO SEU COMPUTADOR</span><h2 id="engine-title">Configurar motor local</h2><p className="modal-intro">O aplicativo usa o ComfyUI instalado no seu computador para gerar com Wan VACE 1.3B, sem conta, créditos ou cobrança por geração.</p>
    <div className={`engine-connection-state ${status?.ready ? 'configured' : ''}`} role="status">{loading || busy ? <LoaderCircle size={17} className="spin" /> : status?.ready ? <ShieldCheck size={17} /> : <Info size={17} />}<span>{loading ? 'Verificando o motor local…' : busy ? 'Conferindo a conexão e os componentes…' : status?.ready ? 'ComfyUI conectado e componentes encontrados.' : 'Inicie o ComfyUI com o modelo e os componentes necessários.'}{status?.gpu?.available && <small className="local-gpu">{status.gpu.name ?? 'Dispositivo detectado'}{status.gpu.vram_gb != null ? ` · ${status.gpu.vram_gb.toFixed(1)} GB de VRAM` : ''}</small>}</span></div>
    <p className="field-help">No Windows com Radeon RX 6600 de 8 GB, o caminho via DirectML é experimental: pode ser lento ou apresentar incompatibilidades. Comece com um trecho de 3 segundos em 480p. A conexão não garante que a geração caiba na memória da placa.</p>
    {error && <div className="inline-error" role="alert">{error}</div>}{message && <div className="engine-settings-message" role="status">{message}</div>}
    <label className="input-label" htmlFor="comfy-url">Endereço do ComfyUI neste computador</label><input id="comfy-url" className="text-input" type="url" autoComplete="off" spellCheck={false} value={url} onChange={event => setUrl(event.target.value)} placeholder="http://127.0.0.1:8188" disabled={loading || busy} autoFocus />
    <p className="field-help">Instale o ComfyUI, o modelo Wan VACE 1.3B e os componentes de pose e vídeo indicados no guia. Inicie o motor antes de verificar. O endereço deve ser local, como 127.0.0.1 ou localhost.</p>
    {status && status.issues.length > 0 && <div className="local-requirements" aria-label="Requisitos pendentes"><strong>O que falta para gerar</strong><ul>{status.issues.map((issue, index) => <li key={`${index}-${issue}`}>{issue}</li>)}</ul></div>}
    <p className="engine-billing-note">A geração local usa seu hardware e energia. A imagem orienta a identidade e o vídeo guia o movimento; revise rosto, mãos e anatomia no resultado.</p>
    <div className="engine-dialog-actions"><button type="submit" className="generate-button" disabled={loading || busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <Settings2 size={16} />} Salvar e verificar</button></div>
  </form></div>
}

function App() {
  const [section, setSection] = useState<'studio' | 'library'>('studio')
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [connected, setConnected] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [character, setCharacter] = useState<Asset | null>(null)
  const [reference, setReference] = useState<Asset | null>(null)
  const [settings, setSettings] = useState<GenerationSettings>(DEFAULT_SETTINGS)
  const [consent, setConsent] = useState({ rights: false, adult: false, nonintimate: false })
  const [uploading, setUploading] = useState<Asset['role'] | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ type: 'error' | 'success' | 'info'; message: string } | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [engineOpen, setEngineOpen] = useState(false)
  const [compare, setCompare] = useState(false)
  const [filter, setFilter] = useState('all')
  const [refreshing, setRefreshing] = useState(false)
  const [assetLibraryOpen, setAssetLibraryOpen] = useState(false)
  const [reviewAsset, setReviewAsset] = useState<Asset | null>(null)
  const [reviewToken, setReviewToken] = useState('')
  const [reviewConsent, setReviewConsent] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [authNeeded, setAuthNeeded] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)
  const [authToken, setAuthToken] = useState('')
  const [authError, setAuthError] = useState<string | null>(null)
  const [authBusy, setAuthBusy] = useState(false)
  const selected = jobs.find(job => job.id === selectedId) ?? null
  const activeCount = jobs.filter(isActive).length
  const completedCount = jobs.filter(isComplete).length
  const desktopMode = capabilities?.desktop_mode === true
  const desktopReview = desktopMode && capabilities?.review.desktop_owner === true
  const openEngine = () => { if (desktopMode) setEngineOpen(true); else setHelpOpen(true) }
  const ready = connected && !authNeeded && capabilities?.provider.configured === true && capabilities?.review.configured === true
  const allConsent = consent.rights && consent.adult && consent.nonintimate
  const mediaApproved = character?.review_status === 'approved' && reference?.review_status === 'approved'
  const durationLimit = Math.min(5, capabilities?.limits.max_duration_video ?? 5)
  const durationMax = Math.max(3, Math.floor(Math.min(durationLimit, (reference?.duration ?? 30) - settings.trim_start)))
  const intervalValid = Number.isFinite(settings.trim_start) && Number.isFinite(settings.duration) && settings.trim_start >= 0 && settings.duration >= 3 && settings.duration <= durationLimit && settings.trim_start + settings.duration <= (reference?.duration ?? 0) + 0.05
  const canGenerate = Boolean(character && reference && intervalValid && mediaApproved && allConsent && ready && !uploading && !submitting)

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true)
    const [capsResult, jobsResult, assetsResult] = await Promise.allSettled([api.capabilities(), api.jobs(), api.assets()])
    if (capsResult.status === 'fulfilled') { setCapabilities(capsResult.value); setConnected(true); setConnectionError(null) }
    else { setConnected(false); setConnectionError(errorMessage(capsResult.reason)) }
    if (jobsResult.status === 'fulfilled') { setJobs(jobsResult.value); setAuthNeeded(false) }
    else if (jobsResult.reason instanceof ApiError && jobsResult.reason.status === 401) {
      setAuthNeeded(true); setJobs([]); setAssets([]); setSelectedId(null); setCharacter(null); setReference(null)
    }
    else if (!quiet) setNotice({ type: 'error', message: `Histórico indisponível: ${errorMessage(jobsResult.reason)}` })
    if (assetsResult.status === 'fulfilled') {
      setAssets(assetsResult.value)
      setCharacter(previous => previous ? assetsResult.value.find(asset => asset.id === previous.id) ?? null : null)
      setReference(previous => previous ? assetsResult.value.find(asset => asset.id === previous.id) ?? null : null)
    }
    if (!quiet) setRefreshing(false)
  }, [])

  useEffect(() => { void refresh(); const interval = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh(true) }, 5000); return () => window.clearInterval(interval) }, [refresh])
  useEffect(() => { if (!notice || notice.type === 'error') return; const timeout = window.setTimeout(() => setNotice(null), 7000); return () => window.clearTimeout(timeout) }, [notice])
  useEffect(() => { if (!helpOpen) return; const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setHelpOpen(false) }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close) }, [helpOpen])

  const upload = async (file: File, role: Asset['role']) => {
    if (uploading) return
    const imageFile = file.type.startsWith('image/') || !file.type && /\.(jpe?g|png|webp)$/i.test(file.name)
    const videoFile = file.type.startsWith('video/') || !file.type && /\.(mp4|mov|webm)$/i.test(file.name)
    if (role === 'reference' && !videoFile) { setNotice({ type: 'error', message: 'A referência de movimento deve ser um vídeo MP4, MOV ou WebM.' }); return }
    if (role === 'character' && !imageFile && !videoFile) { setNotice({ type: 'error', message: 'Escolha uma imagem ou um vídeo para a personagem.' }); return }
    if (file.size > (imageFile ? capabilities?.limits.image_mb ?? 20 : capabilities?.limits.video_mb ?? 150) * 1024 * 1024) { setNotice({ type: 'error', message: `O limite de upload é ${imageFile ? capabilities?.limits.image_mb ?? 20 : capabilities?.limits.video_mb ?? 150} MB por arquivo.` }); return }
    setUploading(role); setNotice(null)
    try {
      const asset = await api.upload(file, role)
      setAssets(previous => [asset, ...previous])
      if (role === 'character') setCharacter(asset)
      else selectReference(asset)
      setNotice({ type: 'success', message: 'Arquivo enviado e analisado.' })
    } catch (error) { setNotice({ type: 'error', message: errorMessage(error) }) }
    finally { setUploading(null) }
  }

  const selectReference = (asset: Asset) => {
    setReference(asset)
    setSettings(previous => ({ ...previous, trim_start: 0, duration: 3 }))
  }

  const removeAsset = async (role: Asset['role']) => {
    const asset = role === 'character' ? character : reference
    if (!asset) return
    setUploading(role)
    try { await api.deleteAsset(asset.id); setAssets(previous => previous.filter(item => item.id !== asset.id)); if (role === 'character') setCharacter(null); else setReference(null); setNotice({ type: 'success', message: 'Arquivo excluído do armazenamento.' }) }
    catch (error) { setNotice({ type: 'error', message: errorMessage(error) }) }
    finally { setUploading(null) }
  }

  const generate = async () => {
    if (!canGenerate || !character || !reference) return
    setSubmitting(true); setNotice(null)
    try {
      const job = await api.createJob(character.id, reference.id, settings)
      setJobs(previous => [job, ...previous.filter(item => item.id !== job.id)]); setSelectedId(job.id); setCompare(false)
      setNotice({ type: 'success', message: 'Geração adicionada à fila. Você pode acompanhar o processamento aqui.' })
    } catch (error) { setNotice({ type: 'error', message: errorMessage(error) }) }
    finally { setSubmitting(false) }
  }

  const cancel = async (job: Job) => {
    setBusyAction(job.id)
    try { const updated = await api.cancelJob(job.id); setJobs(previous => previous.map(item => item.id === job.id ? updated : item)); setNotice({ type: 'info', message: 'Cancelamento solicitado ao motor local. Aguarde o encerramento do processamento.' }) }
    catch (error) { setNotice({ type: 'error', message: errorMessage(error) }) }
    finally { setBusyAction(null) }
  }

  const deleteJob = async (job: Job) => {
    if (!window.confirm('Excluir esta geração e seu resultado armazenado? Esta ação não pode ser desfeita.')) return
    setBusyAction(job.id)
    try { await api.deleteJob(job.id); setJobs(previous => previous.filter(item => item.id !== job.id)); if (selectedId === job.id) setSelectedId(null); setNotice({ type: 'success', message: 'Geração e resultado excluídos.' }) }
    catch (error) { setNotice({ type: 'error', message: errorMessage(error) }) }
    finally { setBusyAction(null) }
  }

  const review = async (decision: 'approved' | 'rejected') => {
    if (!reviewAsset || !desktopReview && !reviewToken.trim() || decision === 'approved' && !reviewConsent) return
    setReviewBusy(true); setReviewError(null)
    try {
      const updated = await api.reviewAsset(reviewAsset.id, desktopReview ? '' : reviewToken.trim(), decision)
      setAssets(previous => previous.map(asset => asset.id === updated.id ? updated : asset))
      setCharacter(previous => previous?.id === updated.id ? updated : previous)
      setReference(previous => previous?.id === updated.id ? updated : previous)
      setReviewAsset(updated); setReviewToken(''); setReviewConsent(false)
      setNotice({ type: 'success', message: decision === 'approved' ? 'Arquivo aprovado após revisão humana.' : 'Arquivo rejeitado. Ele não poderá ser usado em gerações.' })
    } catch (error) { setReviewError(errorMessage(error)) }
    finally { setReviewBusy(false) }
  }

  const login = async () => {
    if (!authToken.trim()) return
    setAuthBusy(true); setAuthError(null)
    try { await api.login(authToken.trim()); setAuthToken(''); setAuthOpen(false); setAuthNeeded(false); await refresh(); setNotice({ type: 'success', message: 'Workspace conectado com uma sessão protegida.' }) }
    catch (error) { setAuthError(errorMessage(error)) }
    finally { setAuthBusy(false) }
  }

  const logout = async () => {
    try {
      await api.logout()
      setJobs([]); setAssets([]); setSelectedId(null); setCharacter(null); setReference(null); setAuthNeeded(true); setCompare(false)
      setNotice({ type: 'info', message: 'Sessão encerrada neste navegador.' })
    } catch (error) { setNotice({ type: 'error', message: errorMessage(error) }) }
  }

  const deleteStoredAsset = async (asset: Asset) => {
    if (!window.confirm(`Excluir “${asset.filename}” do armazenamento?`)) return
    setBusyAction(asset.id)
    try { await api.deleteAsset(asset.id); setAssets(previous => previous.filter(item => item.id !== asset.id)); if (character?.id === asset.id) setCharacter(null); if (reference?.id === asset.id) setReference(null) }
    catch (error) { setNotice({ type: 'error', message: errorMessage(error) }) }
    finally { setBusyAction(null) }
  }

  const retry = (job: Job) => {
    setCharacter(assets.find(asset => asset.id === job.character_id) ?? null)
    setReference(assets.find(asset => asset.id === job.reference_id) ?? null)
    const prior = job.settings ?? DEFAULT_SETTINGS
    setSettings({ quality: prior.quality, model_version: prior.model_version, character_orientation: 'video', keep_original_sound: prior.keep_original_sound, prompt: prior.prompt, duration: Math.max(3, Math.min(5, prior.duration)), trim_start: prior.trim_start, output_fps: prior.output_fps })
    setConsent({ rights: false, adult: false, nonintimate: false }); setSelectedId(null); setSection('studio'); setCompare(false)
    setNotice({ type: 'info', message: 'Arquivos e configurações carregados. Revise a tentativa anterior, confirme as autorizações e clique em GENERATE VIDEO para iniciar uma nova geração local.' })
  }

  const newProject = () => { setSelectedId(null); setCharacter(null); setReference(null); setConsent({ rights: false, adult: false, nonintimate: false }); setSettings(DEFAULT_SETTINGS); setCompare(false); setSection('studio'); setNotice({ type: 'info', message: 'Nova criação iniciada. Selecione os arquivos e confirme as autorizações; seus arquivos anteriores continuam em Meus arquivos.' }) }
  const visibleJobs = jobs.filter(job => filter === 'all' || filter === 'complete' && isComplete(job) || filter === 'active' && isActive(job) || filter === 'failed' && ['failed', 'blocked'].includes(job.status))
  const result = selected ? outputUrl(selected) : null
  const displayProgress = selected?.progress != null && Number.isFinite(selected.progress) ? Math.min(100, Math.max(0, selected.progress)) : null

  const renderJobCard = (job: Job, library = false) => <article key={job.id} className={`history-card ${selectedId === job.id ? 'history-selected' : ''} ${library ? 'library-card' : ''}`}>
    <button className="history-select" onClick={() => { setSelectedId(job.id); setCompare(false); if (library) setSection('studio') }}>
      <span className="history-thumbnail">{job.thumbnail_url ? <img src={job.thumbnail_url} alt="Miniatura da geração" /> : isComplete(job) && outputUrl(job) ? <video src={`${outputUrl(job)}#t=0.1`} preload="metadata" muted /> : <Film size={22} strokeWidth={1.3} />}{isComplete(job) && <span className="thumbnail-play"><Play size={11} fill="currentColor" /></span>}</span>
      <span className="history-text"><span className="history-job-name">Motion {job.id.slice(0, 8)}</span><span className="history-job-date">{formatDate(job.created_at)}</span><StatusPill job={job} /></span>
    </button>
    <div className="history-actions">{isComplete(job) && outputUrl(job) && <a className="icon-button" href={downloadUrl(outputUrl(job)!)} download title="Baixar MP4" aria-label="Baixar MP4"><ArrowDownToLine size={14} /></a>}{isActive(job) ? <button className="icon-button" title="Cancelar geração" aria-label="Cancelar geração" disabled={busyAction === job.id} onClick={() => void cancel(job)}><X size={14} /></button> : <button className="icon-button" title="Excluir geração" aria-label="Excluir geração" disabled={busyAction === job.id} onClick={() => void deleteJob(job)}><Trash2 size={14} /></button>}</div>
  </article>

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand-home" href="#" onClick={event => { event.preventDefault(); setSection('studio') }} aria-label="MAYCOM CHEF CONTROL, início"><Brand /></a>
      <div className="workspace-selector"><span className="workspace-avatar">M</span><div><strong>Meu workspace</strong><span>Estúdio pessoal</span></div><ChevronDown size={13} /></div>
      <span className="nav-label">WORKSPACE</span>
      <nav aria-label="Navegação principal"><button className={`nav-item ${section === 'studio' ? 'active' : ''}`} onClick={() => setSection('studio')}><WandSparkles size={17} /> Motion Studio <span className="nav-new">NEW</span></button><button className={`nav-item ${section === 'library' ? 'active' : ''}`} onClick={() => setSection('library')}><FolderOpen size={17} /> Minhas criações <span className="nav-count">{jobs.length}</span></button></nav>
      <div className="sidebar-divider" /><span className="nav-label">RECURSOS</span><button className="nav-item" onClick={() => setHelpOpen(true)}><CircleHelp size={17} /> Como funciona <ChevronRight size={13} className="nav-chevron" /></button><button className="nav-item" onClick={() => setHelpOpen(true)}><ShieldCheck size={17} /> Uso responsável</button>
      <div className="sidebar-bottom"><div className="engine-card"><span className="engine-icon"><Layers3 size={18} /></span><strong>Potência em cada frame.</strong><p>Identidade e movimento.<br />IA no seu computador.</p><button onClick={openEngine}>Explorar o motor <ArrowRight size={13} /></button></div><div className="sidebar-footer"><span className={`connection-dot ${connected ? 'online' : ''}`} /><span>{connected ? 'Servidor conectado' : 'Sem conexão'}</span><span className="version">v1.1</span></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><span>Workspace</span><ChevronRight size={12} /><strong>{section === 'studio' ? 'Motion Studio' : 'Minhas criações'}</strong></div><div className="topbar-actions"><button type="button" className={`engine-status ${ready ? 'is-ready' : ''}`} onClick={openEngine}><span />{ready ? 'Motor local pronto' : connected ? 'Configurar motor' : 'Aplicativo iniciando'}</button><button className="icon-button" title="Atualizar status" aria-label="Atualizar status" onClick={() => void refresh()} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'spin' : ''} /></button><span className="topbar-divider" /><button className="help-button" onClick={() => setHelpOpen(true)}><CircleHelp size={16} /><span>Ajuda</span></button>{capabilities?.auth_required && !authNeeded && !desktopMode && <button className="icon-button" aria-label="Encerrar sessão" title="Encerrar sessão" onClick={() => void logout()}><LogOut size={16} /></button>}<span className="user-avatar" aria-label="Workspace pessoal">M</span></div></header>
      <main>
        {authNeeded && <div className="configuration-banner auth-banner"><span className="banner-icon"><LockKeyhole size={17} /></span><div><strong>Este workspace é protegido.</strong><p>{desktopMode ? 'A sessão protegida deste aplicativo precisa ser renovada. Feche e abra o MAYCOM CHEF CONTROL novamente.' : 'Conecte-se com o token de acesso do servidor para visualizar e enviar arquivos.'}</p></div>{!desktopMode && <button onClick={() => setAuthOpen(true)}>Conectar <ArrowRight size={13} /></button>}</div>}
        {notice && <div className={`notice notice-${notice.type}`} role={notice.type === 'error' ? 'alert' : 'status'}>{notice.type === 'error' ? <CircleAlert size={17} /> : notice.type === 'success' ? <CheckCircle2 size={17} /> : <Info size={17} />}<span>{notice.message}</span><button className="icon-button" aria-label="Fechar aviso" onClick={() => setNotice(null)}><X size={15} /></button></div>}
        <div className="page-heading"><div><div className="heading-eyebrow"><span className="eyebrow-line" />{section === 'studio' ? 'NEXT GENERATION MOTION CONTROL' : 'SEU ARQUIVO CRIATIVO'}</div><h1>{section === 'studio' ? <>Sua identidade. <span>Em movimento.</span></> : <>Minhas <span>criações.</span></>}</h1><p>{section === 'studio' ? 'Transforme uma referência em novas possibilidades. Você dirige, a inteligência artificial dá vida.' : 'Acompanhe suas gerações, revisite resultados e continue de onde parou.'}</p></div><button className="secondary-button new-project" onClick={newProject}><Plus size={15} /> Nova criação</button></div>
        {!ready && !authNeeded && <div className="configuration-banner"><span className="banner-icon"><Info size={17} /></span><div><strong>{connected ? 'Seu estúdio está pronto para receber os arquivos.' : 'Conecte o backend para começar.'}</strong><p>{connected ? capabilities?.provider.reason ?? (!capabilities?.review.configured ? 'Configure a revisão humana no servidor para liberar os arquivos.' : null) ?? 'Instale e configure o motor local para gerar. Você já pode enviar e organizar seus arquivos.' : connectionError ?? 'Verificando a conexão com o servidor…'}</p></div><button onClick={openEngine}>{desktopMode ? 'Configurar motor local' : 'Como configurar'} <ArrowRight size={13} /></button></div>}
        {section === 'studio' ? <>
          <div className="studio-grid">
            <div className="sources-panel"><div className="panel-section-heading"><span><Layers3 size={15} /> Fontes da criação</span><button className="text-button" onClick={() => setAssetLibraryOpen(true)}><FolderOpen size={12} /> Meus arquivos</button></div><UploadCard role="character" asset={character} onUpload={(file, role) => void upload(file, role)} onRemove={() => void removeAsset('character')} onReview={asset => { setReviewAsset(asset); setReviewError(null); setReviewToken(''); setReviewConsent(false) }} busy={uploading !== null} videoCharacter={true} /><div className="sources-connector"><span /><span className="connector-icon"><Plus size={12} /></span><span /></div><UploadCard role="reference" asset={reference} onUpload={(file, role) => void upload(file, role)} onRemove={() => void removeAsset('reference')} onReview={asset => { setReviewAsset(asset); setReviewError(null); setReviewToken(''); setReviewConsent(false) }} busy={uploading !== null} videoCharacter /><div className="sources-hint"><ShieldCheck size={15} /><p>Crie com responsabilidade.<br /><span>Use apenas mídia autorizada de adultos.</span></p></div></div>
            <section className="preview-panel"><div className="panel-section-heading"><span><Play size={14} /> Preview do resultado</span><span className="live-badge"><span /> OUTPUT</span></div><div className={`preview-stage ${selected && result && isComplete(selected) ? 'with-result' : ''}`}>
              {selected && isActive(selected) ? <div className="processing-preview"><div className="processing-ring"><WandSparkles size={32} strokeWidth={1.3} /></div><span className="eyebrow">PROCESSAMENTO REAL</span><h3>{STATUS_LABELS[selected.status]}</h3><p>{selected.message ?? selected.stage ?? 'Acompanhe o andamento. O resultado aparecerá aqui quando o processamento terminar.'}</p><div className={`progress-track ${displayProgress === null ? 'indeterminate' : ''}`} role="progressbar" aria-label="Progresso da geração" aria-valuenow={displayProgress ?? undefined} aria-valuemin={0} aria-valuemax={100}><span style={displayProgress === null ? undefined : { width: `${displayProgress}%` }} /></div><span className="processing-caption">{displayProgress === null ? 'O motor não informou uma porcentagem de progresso.' : `${Math.round(displayProgress)}% concluído`}</span><button className="text-button" onClick={() => void cancel(selected)} disabled={busyAction === selected.id}>Cancelar geração</button></div>
              : selected && result && isComplete(selected) ? compare ? <ComparisonVideos key={selected.id} job={selected} result={result} /> : <div className="result-content"><div className="comparison-item"><span>{`MOTION ${selected.id.slice(0, 8)}`}</span><video key={result} controls playsInline preload="metadata" src={result} /></div></div>
              : selected && ['failed', 'blocked', 'canceled', 'cancelled'].includes(selected.status) ? <div className="failed-preview"><span className="failed-icon"><CircleAlert size={28} strokeWidth={1.3} /></span><span className="eyebrow">{STATUS_LABELS[selected.status]}</span><h3>{selected.status === 'failed' ? 'A geração não foi concluída.' : 'Geração cancelada.'}</h3><p>{selected.error ?? selected.message ?? 'Confira as configurações e os arquivos antes de tentar novamente.'}</p>{['failed', 'blocked'].includes(selected.status) && <button className="secondary-button" disabled={busyAction === selected.id || !ready} onClick={() => void retry(selected)}><RefreshCw size={14} /> Gerar novamente</button>}</div>
              : <EmptyPreview />}
              <span className="preview-corner corner-tl" /><span className="preview-corner corner-tr" /><span className="preview-corner corner-bl" /><span className="preview-corner corner-br" />
            </div><div className="preview-toolbar"><div className="preview-spec"><span className="spec-dot" /><span>{selected?.settings ? `${selected.settings.quality === 'pro' ? 'Pro' : 'Standard'} · ${selected.settings.output_fps} fps` : 'O resultado aparecerá após a geração'}</span></div>{selected && isComplete(selected) && result ? <div className="preview-actions"><button className={`icon-button ${compare ? 'is-active' : ''}`} title="Comparar referência e resultado" aria-label="Comparar referência e resultado" aria-pressed={compare} onClick={() => setCompare(value => !value)}><Layers3 size={15} /></button><a className="icon-button" href={result} target="_blank" rel="noreferrer" title="Abrir resultado" aria-label="Abrir resultado"><Maximize2 size={15} /></a><a className="small-download" href={downloadUrl(result)} download><ArrowDownToLine size={13} /> MP4</a></div> : <span className="preview-placeholder-icon"><Maximize2 size={14} /></span>}</div><div className="preview-bottom-note"><span className="subtle-badge"><Sparkles size={11} /> MOTION TRANSFER</span><p>A imagem orienta a identidade. Confira cada resultado.</p></div></section>
            <aside className="settings-panel"><div className="panel-section-heading"><span><Settings2 size={15} /> Configurações</span><button className="icon-button" aria-label="Restaurar configurações padrão" title="Restaurar configurações padrão" onClick={() => setSettings(DEFAULT_SETTINGS)}><RefreshCw size={13} /></button></div><div className="settings-content"><div className="setting-label"><label>Etapas de geração</label><span className="small-label">MOTOR LOCAL</span></div><div className="quality-grid"><button className={`quality-option ${settings.quality === 'standard' ? 'selected' : ''}`} onClick={() => setSettings(previous => ({ ...previous, quality: 'standard' }))}><span><Film size={15} /> 20 etapas {settings.quality === 'standard' && <Check size={12} />}</span><small>Menos etapas <span>Menor tempo</span></small></button><button className={`quality-option ${settings.quality === 'pro' ? 'selected' : ''}`} onClick={() => setSettings(previous => ({ ...previous, quality: 'pro' }))}><span><Sparkles size={15} /> 30 etapas {settings.quality === 'pro' && <Check size={12} />}</span><small>Mais etapas <span>Maior tempo</span></small></button></div><p className="field-help">Mais etapas podem aumentar o tempo, sem garantir um resultado melhor. Geração em 480p, com orientação conforme a referência.</p><div className="setting-label model-label"><label htmlFor="model-version">Motor de IA</label></div><div className="select-wrap"><select id="model-version" value="wan-vace" disabled><option value="wan-vace">Wan VACE 1.3B · local</option></select><ChevronDown size={13} /></div>
              <div className="setting-divider" /><div className="setting-label"><label>Referência de movimento</label><Info size={12} /></div><p className="field-help local-motion-note">As poses extraídas do vídeo guiam o movimento. A imagem serve de referência para a personagem.</p>
              <div className="settings-row"><div><label htmlFor="duration">Duração</label><div className="number-wrap"><input id="duration" type="number" min={3} max={durationMax} step={1} value={settings.duration} onChange={event => setSettings(previous => ({ ...previous, duration: Number(event.target.value) }))} onBlur={() => setSettings(previous => ({ ...previous, duration: Math.max(3, Math.min(durationMax, previous.duration || 3)) }))} /><span>s</span></div></div><div><label htmlFor="fps">FPS de saída</label><div className="select-wrap"><select id="fps" value={settings.output_fps} onChange={event => setSettings(previous => ({ ...previous, output_fps: Number(event.target.value) }))}><option value={24}>24 fps</option><option value={30}>30 fps</option></select><ChevronDown size={13} /></div></div></div><p className="field-help local-fps-note">O motor gera a 16 fps. A exportação ajusta para 24 ou 30 fps; isso não corrige os movimentos nem cria detalhes novos.</p><div className="trim-setting"><label htmlFor="trim-start">Início do trecho de referência</label><div className="number-wrap"><input id="trim-start" type="number" min={0} max={Math.max(0, (reference?.duration ?? 30) - 3)} step={0.1} value={settings.trim_start} onChange={event => setSettings(previous => ({ ...previous, trim_start: Math.max(0, Math.min(Math.max(0, (reference?.duration ?? 30) - 3), Number(event.target.value))), duration: 3 }))} /><span>s</span></div></div>
              <div className="setting-divider" /><label className="toggle-row" htmlFor="keep-audio"><span><AudioLines size={15} /><span>Áudio da referência<small>Preservar no resultado</small></span></span><input id="keep-audio" type="checkbox" checked={settings.keep_original_sound} onChange={event => setSettings(previous => ({ ...previous, keep_original_sound: event.target.checked }))} /><span className="toggle-switch" /></label>
              <div className="setting-divider" /><div className="setting-label"><label htmlFor="prompt">Direção criativa</label><span className="small-label">OPCIONAL</span></div><textarea id="prompt" maxLength={1000} value={settings.prompt} placeholder="Descreva o ambiente, a luz e o estilo desejado…" rows={3} onChange={event => setSettings(previous => ({ ...previous, prompt: event.target.value }))} /><div className="prompt-footer"><span>Movimentos vêm do vídeo.</span><span>{settings.prompt.length}/1000</span></div><details className="advanced-notice"><summary><LockKeyhole size={12} /> Controles de identidade <ChevronDown size={12} /></summary><p>A imagem orienta a identidade; confira o resultado. Intensidade, fidelidade facial e corporal não têm ajustes independentes nesta integração.</p></details>
            </div><div className="engine-powered"><span className="powered-symbol">✳</span><div><strong>Wan VACE 1.3B</strong><span>Processamento na sua GPU</span></div><span className={`connection-dot ${ready ? 'online' : ''}`} /></div></aside>
          </div>
          <section className="generate-bar"><div className="generation-consent"><label className="checkbox-row"><input type="checkbox" checked={consent.rights} onChange={event => setConsent(previous => ({ ...previous, rights: event.target.checked }))} /><span>Tenho autorização para usar os arquivos e a imagem das pessoas.</span></label><label className="checkbox-row"><input type="checkbox" checked={consent.adult} onChange={event => setConsent(previous => ({ ...previous, adult: event.target.checked }))} /><span>A personagem é fictícia e todas as pessoas retratadas são adultas.</span></label><label className="checkbox-row"><input type="checkbox" checked={consent.nonintimate} onChange={event => setConsent(previous => ({ ...previous, nonintimate: event.target.checked }))} /><span>Não há conteúdo íntimo ou sexual nem uso não consensual.</span></label></div><div className="generate-action"><button className="generate-button" onClick={() => void generate()} disabled={!canGenerate}>{submitting ? <LoaderCircle size={17} className="spin" /> : <WandSparkles size={17} />}<span>{submitting ? 'ADICIONANDO À FILA…' : 'GENERATE VIDEO'}</span><ArrowRight size={16} /></button><span className="generation-caption">{!ready ? 'Configure o motor local para gerar' : !character || !reference ? 'Adicione os dois arquivos para começar' : !mediaApproved ? 'Os dois arquivos precisam de revisão e aprovação' : !allConsent ? 'Confirme as autorizações para continuar' : !intervalValid ? 'Escolha um trecho válido dentro da referência' : 'Processamento local · sem cobrança por geração'}</span></div></section>
          {selected && <JobDiagnostics job={selected} />}<section className="history-section"><div className="history-heading"><div><h2><History size={16} /> Criações recentes</h2><span>{jobs.length > 0 ? `${jobs.length} ${jobs.length === 1 ? 'geração' : 'gerações'} no workspace` : 'Sua próxima história começa aqui'}</span></div><button className="text-button" onClick={() => setSection('library')}>Ver todas <ArrowRight size={13} /></button></div>{jobs.length ? <div className="history-grid">{jobs.slice(0, 3).map(job => renderJobCard(job))}</div> : <div className="history-empty"><span><Film size={21} strokeWidth={1.2} /></span><div><strong>Ainda não há criações.</strong><p>Seus vídeos e o status das gerações ficarão organizados aqui.</p></div><ArrowRight size={16} /></div>}</section>
        </> : <section className="library-section"><div className="library-stats"><StatCard icon={<Film size={20} />} value={jobs.length} label="Gerações no workspace" /><StatCard icon={<CheckCircle2 size={20} />} value={completedCount} label="Vídeos concluídos" /><StatCard icon={<Clock3 size={20} />} value={activeCount} label="Na fila ou em processamento" /></div><div className="library-toolbar"><div className="filter-tabs" role="tablist" aria-label="Filtrar gerações">{[['all', 'Todas'], ['complete', 'Concluídas'], ['active', 'Em andamento'], ['failed', 'Falhas']].map(([value, label]) => <button key={value} role="tab" aria-selected={filter === value} className={filter === value ? 'selected' : ''} onClick={() => setFilter(value)}>{label}</button>)}</div><span>{visibleJobs.length} {visibleJobs.length === 1 ? 'resultado' : 'resultados'}</span></div>{visibleJobs.length ? <div className="library-grid">{visibleJobs.map(job => renderJobCard(job, true))}</div> : <div className="library-empty"><FolderOpen size={38} strokeWidth={1} /><h2>{jobs.length ? 'Nenhuma geração neste filtro.' : 'Um espaço para suas ideias.'}</h2><p>{jobs.length ? 'Escolha outro filtro para explorar suas criações.' : 'Quando você gerar seu primeiro vídeo, ele aparecerá aqui.'}</p><button className="secondary-button" onClick={() => setSection('studio')}><ArrowLeft size={15} /> Voltar ao estúdio</button></div>}</section>}
        <footer className="main-footer"><span>MAYCOM CHEF CONTROL <span className="footer-separator">/</span> INTELLIGENCE IN MOTION</span><button onClick={() => setHelpOpen(true)}><ShieldCheck size={12} /> Criação responsável</button></footer>
      </main>
    </div>
    {desktopMode && engineOpen && <DesktopEngineDialog onClose={() => setEngineOpen(false)} onConfigured={() => refresh(true)} />}
    {assetLibraryOpen && <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setAssetLibraryOpen(false) }}><section className="help-modal asset-library-modal" role="dialog" aria-modal="true" aria-labelledby="asset-library-title"><div className="modal-header"><span className="modal-icon"><FolderOpen size={22} /></span><button className="icon-button" aria-label="Fechar arquivos" onClick={() => setAssetLibraryOpen(false)} autoFocus><X size={19} /></button></div><span className="eyebrow">ARQUIVOS DO WORKSPACE</span><h2 id="asset-library-title">Sua matéria-prima.</h2><p className="modal-intro">Selecione um arquivo já enviado, revise ou exclua a mídia armazenada.</p>{assets.length ? <div className="asset-library-list">{assets.map(asset => <article className="stored-asset" key={asset.id}><div className="stored-asset-thumb">{asset.kind === 'video' ? <video src={`${assetUrl(asset)}#t=0.1`} preload="metadata" muted /> : <img src={assetUrl(asset)} alt={asset.filename} />}</div><div className="stored-asset-details"><strong>{asset.filename}</strong><span>{asset.role === 'character' ? 'Personagem' : 'Referência'} · {fileSize(asset.size)}</span><span className={`review-badge review-${asset.review_status}`}>{asset.review_status === 'approved' ? 'Aprovado' : asset.review_status === 'rejected' ? 'Rejeitado' : 'Revisão pendente'}</span></div><div className="stored-asset-actions"><button className="text-button" onClick={() => { if (asset.role === 'character') setCharacter(asset); else selectReference(asset); setAssetLibraryOpen(false); setSection('studio') }}>Usar <ArrowRight size={12} /></button><button className="icon-button" title="Revisar arquivo" aria-label="Revisar arquivo" onClick={() => { setReviewAsset(asset); setReviewToken(''); setReviewConsent(false); setReviewError(null) }}><ShieldCheck size={15} /></button><button className="icon-button" title="Excluir arquivo" aria-label="Excluir arquivo" disabled={busyAction === asset.id} onClick={() => void deleteStoredAsset(asset)}><Trash2 size={15} /></button></div></article>)}</div> : <div className="library-empty small"><ImagePlus size={30} strokeWidth={1.3} /><p>Você ainda não enviou arquivos.</p></div>}<p className="field-help library-disclosure">A geração usa o motor local. O ComfyUI mantém cópias em input e output; excluir no app não apaga essas cópias.</p></section></div>}
    {reviewAsset && <div className="modal-backdrop review-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !reviewBusy) { setReviewAsset(null); setReviewToken('') } }}><section className="help-modal review-modal" role="dialog" aria-modal="true" aria-labelledby="review-title"><div className="modal-header"><span className="modal-icon"><ShieldCheck size={22} /></span><button className="icon-button" aria-label="Fechar revisão" disabled={reviewBusy} onClick={() => { setReviewAsset(null); setReviewToken('') }} autoFocus><X size={19} /></button></div><span className="eyebrow">REVISÃO HUMANA</span><h2 id="review-title">Autorização antes da criação.</h2><p className="modal-intro">{desktopReview ? 'Confira a mídia e confirme as condições de uso antes de aprová-la.' : 'Um operador autorizado deve revisar a mídia.'} Esta revisão não é um detector automático de idade, identidade ou consentimento.</p><div className="review-media">{reviewAsset.kind === 'video' ? <video controls playsInline preload="metadata" src={assetUrl(reviewAsset)} /> : <img src={assetUrl(reviewAsset)} alt="Arquivo em revisão" />}</div><div className="review-file-info"><strong>{reviewAsset.filename}</strong><span className={`review-badge review-${reviewAsset.review_status}`}>{reviewAsset.review_status === 'approved' ? 'Aprovado' : reviewAsset.review_status === 'rejected' ? 'Rejeitado' : 'Pendente'}</span></div>{!capabilities?.review.configured && <div className="inline-warning"><Info size={15} /><span>{desktopMode ? 'A revisão ainda não está disponível. Feche e abra o aplicativo novamente.' : 'O operador precisa configurar MAYCOM_REVIEW_TOKEN no servidor para habilitar a revisão.'}</span></div>}{reviewError && <div className="inline-error" role="alert">{reviewError}</div>}{!desktopReview && <><label className="input-label" htmlFor="review-token">Token do operador</label><input id="review-token" className="text-input" type="password" autoComplete="off" value={reviewToken} onChange={event => setReviewToken(event.target.value)} placeholder="Token de revisão configurado no servidor" /><p className="field-help">O token permanece somente em memória e é descartado ao fechar.</p></>}<label className="checkbox-row review-checkbox"><input type="checkbox" checked={reviewConsent} onChange={event => setReviewConsent(event.target.checked)} /><span>Revisei o arquivo: a personagem é adulta e fictícia, todas as pessoas são adultas, não há conteúdo íntimo e o uso é autorizado.</span></label><div className="review-buttons"><button className="secondary-button danger-button" disabled={reviewBusy || !desktopReview && !reviewToken.trim() || !capabilities?.review.configured} onClick={() => void review('rejected')}><X size={15} /> Rejeitar</button><button className="generate-button" disabled={reviewBusy || !desktopReview && !reviewToken.trim() || !reviewConsent || !capabilities?.review.configured} onClick={() => void review('approved')}>{reviewBusy ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />} Aprovar arquivo</button></div></section></div>}
    {authOpen && <div className="modal-backdrop auth-backdrop" role="presentation"><form className="help-modal auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title" onSubmit={event => { event.preventDefault(); void login() }}><div className="modal-header"><span className="modal-icon"><LockKeyhole size={22} /></span><button type="button" className="icon-button" aria-label="Fechar acesso" onClick={() => { setAuthOpen(false); setAuthToken('') }}><X size={19} /></button></div><span className="eyebrow">WORKSPACE PROTEGIDO</span><h2 id="auth-title">Seu estúdio, em segurança.</h2><p className="modal-intro">Use o token de acesso configurado pelo administrador no servidor.</p>{authError && <div className="inline-error" role="alert">{authError}</div>}<label className="input-label" htmlFor="access-token">Token de acesso</label><input id="access-token" type="password" className="text-input" value={authToken} onChange={event => setAuthToken(event.target.value)} autoComplete="off" autoFocus placeholder="Digite o token do workspace" /><p className="field-help">O token não é salvo no navegador. O servidor cria uma sessão protegida para acessar seus arquivos.</p><button type="submit" className="generate-button auth-submit" disabled={!authToken.trim() || authBusy}>{authBusy ? <LoaderCircle size={16} className="spin" /> : <LockKeyhole size={16} />} Conectar workspace</button></form></div>}
    {helpOpen && <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setHelpOpen(false) }}><section className="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title"><div className="modal-header"><span className="modal-icon"><WandSparkles size={22} /></span><button className="icon-button" aria-label="Fechar ajuda" onClick={() => setHelpOpen(false)} autoFocus><X size={19} /></button></div><span className="eyebrow">MAYCOM CHEF CONTROL</span><h2 id="help-title">Da sua ideia ao movimento.</h2><p className="modal-intro">Um fluxo de criação conectado a um motor real de inteligência artificial.</p><div className="help-steps"><div><span>01</span><div><strong>Defina a identidade</strong><p>Envie uma imagem ou vídeo de uma personagem adulta fictícia. Em vídeos, o primeiro frame representa sua identidade.</p></div></div><div><span>02</span><div><strong>Escolha o movimento</strong><p>Envie a referência, selecione o trecho e ajuste a qualidade. Use uma pessoa, sem cortes e com o corpo visível.</p></div></div><div><span>03</span><div><strong>Gere e acompanhe</strong><p>Confirme as autorizações e aguarde a revisão. O vídeo será gerado na GPU configurada, processado e salvo no histórico para preview e download.</p></div></div></div><div className="modal-configuration"><h3><Settings2 size={16} /> Motor local, sem créditos</h3><p>{ready ? 'O ComfyUI está conectado e os componentes foram encontrados. Comece com uma geração curta para testar o dispositivo configurado.' : desktopMode ? 'Instale e inicie o ComfyUI neste computador com Wan VACE 1.3B e os componentes de pose e vídeo. Depois, abra Configurar motor local para verificar a conexão.' : 'O administrador precisa instalar e iniciar o ComfyUI no computador do backend com Wan VACE 1.3B e os componentes necessários.'}</p><p className="field-help">Não é necessária uma conta de API. O motor e os modelos são instalados separadamente. Em uma Radeon RX 6600 de 8 GB no Windows, DirectML é experimental; comece com trechos de 3 segundos. A velocidade e a compatibilidade dependem do dispositivo e das dependências. Rosto, mãos, anatomia e fidelidade dos movimentos precisam de revisão; não há garantia de movimentos perfeitos.</p>{desktopMode && <button type="button" className="secondary-button" onClick={() => { setHelpOpen(false); setEngineOpen(true) }}><Settings2 size={14} /> Configurar motor local</button>}</div><div className="modal-safety"><ShieldCheck size={18} /><p>Somente adultos e mídia autorizada. Conteúdo íntimo, sexual, envolvendo menores ou sem consentimento não é permitido. Você pode excluir seus arquivos e resultados do armazenamento do aplicativo.</p></div><button className="secondary-button modal-close" onClick={() => setHelpOpen(false)}>Entendi <ArrowRight size={14} /></button></section></div>}
  </div>
}

function StatCard({ icon, value, label }: { icon: ReactNode; value: number; label: string }) { return <div className="stat-card"><span>{icon}</span><strong>{value}</strong><small>{label}</small></div> }
export default App
