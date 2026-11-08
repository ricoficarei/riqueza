# MAYCOM CHEF CONTROL 1.1.0 — validação do modo local

## Verificado neste ambiente

- 85 testes do backend passaram na suíte completa; um teste adicional do pipeline
  local também passou isoladamente (86 testes distintos ao todo).
- Build TypeScript/Vite e 3 testes de segurança da janela passaram.
- Navegador real com backend real: sessão privada, configuração local salva,
  URL externa rejeitada, conexão paga removida com HTTP410, geração bloqueada
  sem ComfyUI, layout desktop/celular sem overflow e nenhum erro JavaScript.
- O adaptador foi exercitado com respostas HTTP controladas explicitamente de
  teste: diagnóstico de componentes, workflow referência+pose, fila, download,
  proteção de caminhos e cancelamento. Não são inferências reais.
- FFmpeg real normalizou referência para 16 FPS/480p, restaurou áudio e exportou
  MP4. O vídeo sintético da fixture foi identificado como dublê de teste.
- Self-test do backend desktop em Linux passou 24 verificações sem inferência.

## Ainda não validado

Nenhuma geração de Wan VACE foi executada nesta máquina. Não há GPU AMD ou NVIDIA
nesta instância. A instalação DirectML, o consumo de RAM/VRAM, a velocidade e a
execução de todos os operadores em Radeon RX 6600 continuam sem validação.
Não foi comprovada preservação de rosto, qualidade das mãos, perfeição anatômica
ou fidelidade dos movimentos. Os modelos de cerca de 15 GB não estão incluídos.

Abertura do portátil em Windows 10/11 físico ainda precisa ser testada. Testes em
Linux/Wine do backend não equivalem a esse teste nem a uma geração real.

A versão anterior 1.0.1 não é atualizada automaticamente e continua exigindo
créditos. Use a versão local 1.1.0 para não utilizar o serviço pago.

## Backend Windows empacotado

O executável Windows compilado com PyInstaller passou **23 verificações reais
no Wine**, sem consultar o fonte para executar o app: sessão privada, configuração
local persistida, API paga removida, upload, mídia FFmpeg/FFprobe/OpenCV, revisão
e exclusão. O relatório registra `frozen=true`, `platform=win32` e `passed=true`.
Isso não valida a janela Electron em Windows físico nem o motor DirectML.
