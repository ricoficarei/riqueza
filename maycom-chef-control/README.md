# MAYCOM CHEF CONTROL 1.1.0 — IA local experimental

Transferência de movimentos por **ComfyUI local + Wan2.1 VACE 1.3B + DWPose**.
Sem conta fal, créditos ou chamadas de inferência paga. Os modelos e o motor são
instalados separadamente; este repositório e o portátil não incluem esses pesos.

**Radeon RX 6600 de 8 GB / Windows:** DirectML é uma rota experimental. A geração
não foi validada nessa GPU neste ambiente. A qualidade, o uso de memória e a
velocidade precisam de teste real. Não há garantia de movimentos perfeitos,
identidade exata, mãos corretas ou desempenho equivalente a modelos maiores.

## Instalar e usar

1. Siga [o guia de instalação do motor local](docs/LOCAL-GRATUITO.md).
   Os modelos somam cerca de 15 GB, além das dependências. RAM também importa.
2. Inicie o ComfyUI numa instância dedicada, em `http://127.0.0.1:8188`.
3. Abra o portátil 1.1.0 e clique **Configurar motor local**. O app verifica
   conexão, GPU reportada, nós e nomes dos modelos; isso não é um benchmark.
4. Envie personagem e referência, revise os arquivos e confirme as autorizações.
5. Comece com 3 segundos e 20 etapas. Gere, revise o resultado e baixe o MP4.

Modo inicial: 480p (832×480 ou 480×832), trechos de 3–5 segundos, 20 ou 30 etapas.
O motor gera a 16 FPS. Exportar a 24/30 FPS repete/remove quadros; não adiciona
movimentos inferidos. Vídeo da personagem usa o primeiro frame como referência.

## Desenvolvimento

Linux: Python 3.12+, Node.js 22+, FFmpeg/FFprobe. `bash setup.sh` instala pelos
lockfiles e constrói a interface; `bash start.sh` inicia o app. Configure
`MAYCOM_COMFY_URL`, `MAYCOM_ACCESS_TOKEN` e `MAYCOM_REVIEW_TOKEN` no processo.
Não há chave fal. O servidor precisa alcançar o ComfyUI na mesma máquina.
Configurações pela interface são exclusivas do desktop autenticado; no servidor
use a variável `MAYCOM_COMFY_URL`.

`bash test.sh` testa backend e build. `cd desktop-shell && npm test` verifica
segurança da janela. `backend/.venv/bin/python -m pytest desktop/test_launcher.py`
verifica autenticação, protocolo de inicialização e encerramento do desktop.
Os testes usam dublês explícitos de inferência e mídia sintética identificada;
nenhum teste é evidência de qualidade de uma geração real.

## Implementação

- Upload privado, inspeção real por FFmpeg/OpenCV, revisão e exclusão local.
- Fila persistente, cancelamento, histórico e MP4 reproduzível/baixável.
- Preparo real da referência a 16 FPS e 480p, pose DWPose ONNX, imagem de referência
  em WanVaceToVideo, amostragem neural, remoção do latente da referência,
  decodificação em blocos, áudio opcional e exportação MP4.
- T5 na CPU para reduzir uso de VRAM; não são usados pesos FP8.
- Somente loopback HTTP no adaptador, sem proxy/redirect/URL externa ou fallback
  para APIs pagas. A conexão fal antiga retorna HTTP410 e chaves antigas são ignoradas.
- Tarefas interrompidas não são reenviadas automaticamente. Tarefas da versão
  antiga não são retomadas no motor novo.

O ComfyUI guarda cópias em `input/` e `output/maycom/`. Excluir no app não remove
essas cópias. Use uma instância dedicada: a interrupção do ComfyUI é global.
Fechar a janela não necessariamente encerra o ComfyUI, que é um processo separado.

O portátil inclui janela Electron, backend Python e FFmpeg; a instalação separada
do ComfyUI/modelos ainda é necessária. [Guia de build](desktop-shell/README.md).
A versão 1.0.1 já baixada não é atualizada automaticamente.

A revisão e as métricas visuais não verificam consentimento, idade ou anatomia.
Use mídia autorizada de adultos fictícios em cenas não íntimas e revise o vídeo.
Documentos anteriores sobre Kling/fal são históricos; não descrevem o caminho
ativo de geração desta versão.
