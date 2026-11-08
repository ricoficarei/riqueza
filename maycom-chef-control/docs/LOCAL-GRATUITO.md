# MAYCOM CHEF CONTROL — geração local sem créditos

## Caminho para Windows com Radeon RX 6600 de 8 GB

O motor oficial Wan2.2-Animate-14B descrito mais abaixo depende de CUDA/NVIDIA e **não é a escolha para a Radeon RX 6600**. Para esse computador, a alternativa implementada no app é uma conexão local com ComfyUI e **Wan2.1-VACE-1.3B**, usando DWPose para extrair a pose do vídeo e a imagem enviada como referência visual. É geração neural com orientação por movimentos; o modelo menor pode perder detalhes, rosto, mãos e consistência.

Esta rota é **experimental**: a integração foi preparada a partir das interfaces e dos nós oficiais, mas não houve execução de inferência em uma RX 6600 neste ambiente. O fato de os pesos de difusão ocuparem cerca de 4 GB não assegura caber em 8 GB durante toda a geração. O codificador de texto fica na RAM do computador; a RAM e a memória de trabalho também precisam ser suficientes. Comece com resolução e duração baixas e aumente somente depois de um teste real bem-sucedido.

O ComfyUI oferece uma rota DirectML para AMD no Windows nas versões documentadas abaixo. Não é necessário comprar uma GPU NVIDIA para tentar essa rota. Não se afirma suporte ROCm oficial específico à RX 6600, nem que o driver e o conjunto de dependências do computador já estejam compatíveis.

### Preparar ComfyUI com DirectML

Use uma instalação separada do ComfyUI, fora do diretório do app. O código-fonte consultado foi **ComfyUI v0.3.40**, que contém os nós VACE e documenta `--directml`. A versão PyPI `torch-directml==0.2.5.dev240914` depende de `torch==2.4.1` e `torchvision==0.19.1`; há wheels Windows para Python 3.10 a 3.12. Não use Python 3.13 com essa versão DirectML nem misture uma versão PyTorch diferente.

Exemplo de preparação no PowerShell, com Python 3.11 já instalado. Os comandos são instruções de instalação experimental, **não um registro de instalação validada no Windows**:

```powershell
git clone --branch v0.3.40 https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
@'
torch==2.4.1
torchvision==0.19.1
torchaudio==2.4.1
numpy==1.26.4
transformers==4.49.0
'@ | Set-Content -Encoding ascii directml-constraints.txt
.\.venv\Scripts\python.exe -m pip install -c directml-constraints.txt torch-directml==0.2.5.dev240914
.\.venv\Scripts\python.exe -m pip install -c directml-constraints.txt -r requirements.txt
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git custom_nodes/comfyui_controlnet_aux
git -C custom_nodes/comfyui_controlnet_aux checkout 15847e6adc92bbdfdbf1ce3391579498f80e35e1
.\.venv\Scripts\python.exe -m pip install -c directml-constraints.txt -r custom_nodes/comfyui_controlnet_aux/requirements.txt
.\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime-gpu
.\.venv\Scripts\python.exe -m pip install onnxruntime
```

O DWPose usa os arquivos ONNX `yolox_l.onnx` e `dw-ll_ucoco_384.onnx`, com processamento de pose na CPU. O nó pode baixar esses arquivos na primeira utilização. Para uso sem internet, prepare seu cache antes. O processamento neural principal continua no dispositivo DirectML. A instalação de CUDA ou `onnxruntime-gpu` não acelera a Radeon por si só.

O pacote de pose pode instalar `onnxruntime-gpu`; os comandos acima o removem e
mantêm o runtime CPU para essa configuração AMD.

Inicie o serviço local e mantenha sua janela aberta:

```powershell
$env:AUX_ORT_PROVIDERS="CPUExecutionProvider"
.\.venv\Scripts\python.exe main.py --directml --lowvram --force-fp16 --cpu-vae --use-split-cross-attention --listen 127.0.0.1 --port 8188
```

O descarregamento de memória e o VAE na CPU reduzem pressão sobre VRAM e podem tornar a geração muito lenta. Não há previsão de duração validada na RX 6600. Caso algum operador DirectML falhe, guarde a mensagem de erro; presença de arquivos ou uma conexão HTTP bem-sucedida não comprova que todos os operadores do modelo funcionarão nessa GPU.

### Pesos do modelo menor

Baixe os três arquivos e mantenha exatamente estes nomes e locais na instalação ComfyUI:

| Pasta dentro de ComfyUI | Arquivo | Download oficial indicado pelo projeto ComfyUI |
| --- | --- | --- |
| `models/diffusion_models/` | `wan2.1_vace_1.3B_fp16.safetensors` | [Modelo VACE 1.3B, aproximadamente 4,01 GB](https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_vace_1.3B_fp16.safetensors) |
| `models/text_encoders/` | `umt5_xxl_fp16.safetensors` | [Codificador de texto FP16, aproximadamente 10,59 GB](https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp16.safetensors) |
| `models/vae/` | `wan_2.1_vae.safetensors` | [VAE, aproximadamente 242 MB](https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors) |

O codificador é carregado na CPU pelo fluxo do aplicativo. **Não substitua pelos pesos FP8** nessa configuração DirectML. Não há uso de LoRA CausVid ou promessa de aceleração de quatro passos. Os modelos são downloads grandes, somando cerca de 15 GB antes das dependências e dos caches.

### Usar pelo app

Selecione a opção local ComfyUI e configure o servidor `http://127.0.0.1:8188`. O backend e o ComfyUI devem estar na mesma máquina. A rota usa somente esse serviço local, sem chave fal ou conta com créditos. A interface consulta os nós e os nomes dos modelos disponíveis; erros na preparação devem ser resolvidos antes da inferência.

O app prepara os quadros do trecho escolhido, extrai a pose com `DWPreprocessor`, fornece imagem e pose ao `WanVaceToVideo`, amostra um vídeo novo, remove o quadro latente extra da referência e salva a saída. Um MP4 pronto ou uma cópia da referência não substituem a geração. O FPS e a duração escolhidos precisam ser respeitados pelo fluxo; o modelo exige comprimentos no formato 4n+1 e isso pode introduzir arredondamento.

A instalação acima não altera automaticamente o executável 1.0.1 já baixado. É necessário usar uma versão do app que contenha o adaptador local. Sem os pesos e o motor preparados, a opção local não deve anunciar que uma geração está disponível nem recorrer a serviços pagos.

Fontes desta rota:

- [ComfyUI v0.3.40: DirectML no Windows](https://github.com/Comfy-Org/ComfyUI/blob/v0.3.40/README.md#directml-amd-cards-on-windows)
- [Nós VACE e remoção do latente de referência](https://github.com/Comfy-Org/ComfyUI/blob/v0.3.40/comfy_extras/nodes_wan.py)
- [Fluxo oficial VACE com referência e controle; inclui variante 1.3B](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_wan_vace_14B_v2v.json)
- [DWPose e esquema do nó `DWPreprocessor`](https://github.com/Fannovel16/comfyui_controlnet_aux/blob/15847e6adc92bbdfdbf1ce3391579498f80e35e1/node_wrappers/dwpose.py)
- [Dependências e wheels do DirectML](https://pypi.org/project/torch-directml/0.2.5.dev240914/)

## Alternativa com NVIDIA: Wan2.2-Animate-14B

A integração local usa **Wan2.2-Animate-14B**, o modelo de animação de personagens publicado pela equipe Wan. A inferência ocorre em uma GPU do computador que executa o motor. Não exige conta fal, chave fal ou créditos por geração. O download inicial dos modelos exige internet; depois de baixar os arquivos completos, o motor pode trabalhar sem acesso ao serviço fal.

Software sem cobrança por geração não fornece hardware gratuito: há consumo de energia, espaço em disco e tempo de processamento. Se o computador não tiver GPU compatível ou memória suficiente, remover a integração paga não cria essa capacidade. Não existe garantia de movimentos perfeitos, preservação completa do rosto ou superioridade sobre Kling.

## Estado desta alteração

O app passa a poder chamar o pré-processamento e a inferência reais do repositório oficial Wan. Os arquivos grandes do modelo, PyTorch/CUDA e o ambiente de inferência são instalados separadamente; não estão embutidos no executável Windows anterior. Este ambiente de desenvolvimento não tem GPU NVIDIA disponível, portanto **nenhum vídeo foi gerado com o motor local nesta entrega**. Testes de integração com processos de teste verificam o código do app, não a qualidade do modelo.

O caminho de referência para instalar o motor é Linux com NVIDIA/CUDA. O código oficial depende de componentes como FlashAttention e Decord. A instalação nativa dessas dependências e a inferência em Windows não foram validadas aqui. A existência de uma GPU NVIDIA no Windows não comprova que o ambiente Python do motor esteja preparado.

## Hardware e arquivos

O modelo tem 14 bilhões de parâmetros e exige vários arquivos grandes, além de memória RAM e GPU. Os requisitos efetivos variam com a resolução e a versão das dependências. A implementação oficial carrega o transformador em CUDA; opções de descarregamento para RAM não asseguram execução em placas pequenas. Não se anuncia compatibilidade garantida com 8, 12, 16 ou 24 GiB de VRAM.

Antes de baixar dezenas de gigabytes, confira a GPU e a memória disponíveis com `nvidia-smi`. Uma GPU com bastante VRAM e RAM ampla é o ponto de partida para a implementação oficial; redução de resolução pode diminuir a memória das ativações, mas não elimina o tamanho dos pesos. Sem GPU compatível, o aplicativo deve informar a indisponibilidade e não recorrer à fal.

Use a distribuição **original** `Wan-AI/Wan2.2-Animate-14B` com o script oficial. A distribuição `Wan2.2-Animate-14B-Diffusers` e pesos reempacotados para ComfyUI têm organização diferente e não são intercambiáveis com esse comando.

Arquivos esperados no diretório do modelo incluem:

```text
Wan2.2-Animate-14B/
  config.json
  diffusion_pytorch_model*.safetensors
  models_t5_umt5-xxl-enc-bf16.pth
  models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth
  Wan2.1_VAE.pth
  google/umt5-xxl/
  xlm-roberta-large/
  process_checkpoint/
    det/yolov10m.onnx
    pose2d/vitpose_h_wholebody.onnx
```

Quando o transformador vier fragmentado, mantenha seu índice e todos os fragmentos. Use o snapshot oficial completo para evitar arquivos de configuração ou tokenização ausentes. O modo de animação simples não usa substituição de personagem, SAM2 nem FLUX; algumas bibliotecas de SAM2 ainda são importadas pelo pré-processador oficial e precisam estar instaladas.

## Preparar o ambiente do motor

Os comandos abaixo documentam o procedimento do projeto oficial. Não foram executados com GPU nesta máquina. Escolha uma versão de Python, PyTorch e CUDA compatíveis com os requisitos atuais do repositório e com o driver NVIDIA. Não instale esses pacotes dentro do ambiente leve do backend do app.

```bash
git clone https://github.com/Wan-Video/Wan2.2.git
cd Wan2.2
git checkout 1ea34ff48f87168174e12956e200b1d908b1c5ff
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# Instale PyTorch/CUDA seguindo o seletor oficial: https://pytorch.org/get-started/locally/
python -m pip install -r requirements.txt -r requirements_animate.txt
python -c 'import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CUDA indisponível")'
```

FlashAttention pode exigir compilação, toolkit CUDA e compilador compatíveis. Se a instalação falhar, resolva o erro no ambiente do motor antes de configurá-lo no app. Não é suficiente instalar apenas o pacote `torch` no backend.

Baixe os pesos pela página oficial do modelo ou pela CLI oficial do Hugging Face. Exemplo, em ambiente com o comando `hf` instalado:

```bash
hf download Wan-AI/Wan2.2-Animate-14B --local-dir /caminho/modelos/Wan2.2-Animate-14B
```

A ferramenta de download não cobra inferência. Não forneça tokens de contas em arquivos de código nem em conversas. Este ambiente de desenvolvimento pode restringir os destinos de download; isso é independente da possibilidade de baixar os arquivos em seu computador.

## Conferir o motor antes de usar pelo app

Com uma imagem e um vídeo autorizados, execute no diretório do repositório Wan e no ambiente Python do motor:

```bash
python wan/modules/animate/preprocess/preprocess_data.py \
  --ckpt_path /caminho/modelos/Wan2.2-Animate-14B/process_checkpoint \
  --video_path /caminho/entrada/referencia.mp4 \
  --refer_path /caminho/entrada/personagem.png \
  --save_path /caminho/saida/preparado \
  --resolution_area 832 480 \
  --fps 30

python generate.py \
  --task animate-14B \
  --ckpt_dir /caminho/modelos/Wan2.2-Animate-14B \
  --src_root_path /caminho/saida/preparado \
  --refert_num 1 \
  --save_file /caminho/saida/resultado.mp4 \
  --offload_model True \
  --convert_model_dtype \
  --t5_cpu \
  --sample_steps 20
```

O pré-processador extrai movimentos e recortes faciais, criando `src_pose.mp4`, `src_face.mp4` e `src_ref.png`. O vídeo bruto não pode ser usado diretamente no lugar desses sinais. O modo simples replica os sinais de pose extraídos; a correção avançada de proporções com FLUX não faz parte desta integração. A equipe Wan também avisa que o retargeting não garante resultados perfeitos.

A inferência oficial usa 30 FPS; esse valor deve ser mantido no pré-processamento para preservar a duração. O parâmetro de geração `frame_num`, cujo padrão é 77, é o comprimento de segmento, não uma garantia de limitar a saída a 77 quadros: o motor processa os segmentos do vídeo. Resolução de processamento é uma área-alvo, preservando a proporção e os múltiplos exigidos pelo modelo.

## Configurar o app

Configure o modo local com três caminhos absolutos: executável Python do ambiente de inferência, diretório do repositório Wan e diretório do modelo original. Esses caminhos devem existir na mesma máquina do backend. Um Python dentro de WSL não é um executável Windows utilizável diretamente pelo backend Windows; executar o conjunto em Linux é o caminho de referência desta integração.

Confirme o diagnóstico do motor na interface antes de gerar. Ter arquivos presentes e CUDA detectável não substitui um teste de inferência. Arquivos passam pela revisão existente do estúdio; a seleção local não envia os arquivos à fal. A saída real é validada e exportada pelo FFmpeg do aplicativo.

Comece com vídeo curto, uma só pessoa e enquadramento de corpo inteiro, sem cortes abruptos nem obstruções. Confira rosto, mãos, roupas e continuidade do MP4. Mais resolução e mais passos aumentam processamento, mas não asseguram melhor anatomia.

## Licenças e fontes verificadas

O repositório Wan declara Apache 2.0 para seus modelos. Preserve os avisos e confira também as licenças das dependências e dos modelos auxiliares antes de redistribuir pesos ou instaladores completos. Esta alteração não inclui pesos nem pacotes de terceiros.

- Código, licença e comandos: https://github.com/Wan-Video/Wan2.2
- Versão de código consultada: https://github.com/Wan-Video/Wan2.2/tree/1ea34ff48f87168174e12956e200b1d908b1c5ff
- Guia de pré-processamento: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/modules/animate/preprocess/UserGuider.md
- Modelo original, indicado pelo repositório Wan: https://huggingface.co/Wan-AI/Wan2.2-Animate-14B
- Pipeline Diffusers e pré-processamento obrigatório: https://github.com/huggingface/diffusers/blob/main/docs/source/en/api/pipelines/wan.md
- Alternativa ComfyUI, com instalação própria e fluxos diferentes: https://github.com/Comfy-Org/docs/blob/main/tutorials/video/wan/wan2-2-animate.mdx

ComfyUI local também não cobra por inferência no hardware próprio, mas Comfy Cloud é um serviço separado e não está incluído. Os pesos FP8 e os fluxos do ComfyUI não são suportados pelo adaptador de comandos oficiais descrito acima.

## Cópias no motor local

O ComfyUI guarda entradas em `input/` e saídas em `output/maycom/`. A exclusão
no app remove somente os arquivos do app; remova essas cópias separadamente.
Use uma instância dedicada: o endpoint de interrupção do ComfyUI é global.

O modo inicial do aplicativo limita a geração a 480p e 3–5 segundos, com 20 ou
30 etapas. O VACE 1.3B gera a 16 FPS neste fluxo; a seleção 24/30 FPS é somente
exportação. O áudio da referência pode ser copiado para o resultado.

Veja também `VALIDATION-LOCAL.md` para distinguir testes de integração e geração.
