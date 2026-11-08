# MAYCOM CHEF CONTROL — modelos e limites verificados

Pesquisa técnica consultada em 5 de novembro de 2026. As fontes abaixo são dos responsáveis pelos modelos ou SDKs. A consulta de páginas `fal.ai` foi recusada pelo proxy deste ambiente; o contrato da API foi conferido nos tipos gerados do SDK oficial, commit `a29c8955d51c7e9009091b43dca4f10660f721ae` (4 de novembro de 2026). Isso confirma a interface publicada, mas não comprova acesso da conta, preços, disponibilidade ou qualidade de uma geração real.

## Escolha para a versão construída

O adaptador comercial usa Kling Motion Control via fal. Ele recebe uma imagem de identidade e um vídeo que conduz o movimento, executa inferência remota e devolve um vídeo novo. A execução depende de conta/créditos fal, `FAL_KEY` configurada somente no servidor e acesso HTTPS aos serviços do provedor. A máquina local não precisa de GPU para esse modo.

Kling v3 é a escolha padrão recomendada porque o contrato oficial oferece um recurso adicional de referência facial. V2.6 continua sendo uma alternativa com o mesmo contrato básico. Essa escolha não implica superioridade visual comprovada: não foi executado um benchmark entre eles nem contra a referência comercial mencionada no pedido. Não foi verificado um endpoint oficial “Kling 4.0 Motion Control”; o aplicativo não deve divulgar esse nome como motor integrado.

Wan2.2-Animate-14B é a opção aberta indicada para uma implantação futura ou um worker próprio de GPU. A pesquisa e os comandos abaixo não significam que seus pesos foram baixados, que a inferência foi executada ou que esse motor esteja integrado à versão corrente. Consulte o README e a configuração efetiva do aplicativo para distinguir o adaptador entregue das alternativas estudadas.

| Opção verificada | Entrada de identidade | Direção do movimento | Diferença comprovada | Dependência |
| --- | --- | --- | --- | --- |
| Kling v3 standard/pro Motion Control | Imagem | Vídeo | `elements` opcional para vínculo facial | API paga fal |
| Kling v2.6 standard/pro Motion Control | Imagem | Vídeo | Contrato básico sem `elements` | API paga fal |
| Wan2.2-Animate-14B | Imagem, pose e expressão pré-processadas | Vídeo | Modos animation e replacement; implementação aberta | CUDA e pesos grandes |

## Contrato Kling confirmado

Endpoints publicados no SDK oficial:

```text
fal-ai/kling-video/v3/standard/motion-control
fal-ai/kling-video/v3/pro/motion-control
fal-ai/kling-video/v2.6/standard/motion-control
fal-ai/kling-video/v2.6/pro/motion-control
```

Entrada comum:

```json
{
  "image_url": "https://URL-da-imagem-enviada",
  "video_url": "https://URL-do-video-enviado",
  "character_orientation": "video",
  "prompt": "The adult fictional character follows the reference movement.",
  "keep_original_sound": true,
  "enable_safety_checker": true
}
```

`image_url`, `video_url` e `character_orientation` são obrigatórios. `prompt`, `keep_original_sound` e `enable_safety_checker` são opcionais no serviço; o aplicativo mantém a verificação de segurança ativada. O SDK declara que desativá-la exige autorização de conta e que requisições sem autorização continuam verificadas.

As orientações têm efeitos diferentes:

- `video`: orientação do personagem acompanha o vídeo; indicada pelo provedor para movimentos complexos; máximo publicado de 30 segundos.
- `image`: orientação acompanha a imagem; indicada para seguir movimentos de câmera; máximo publicado de 10 segundos.

A imagem deve mostrar proporções claras, sem obstrução, com o personagem ocupando mais de 5% da área. O vídeo deve mostrar uma pessoa em estilo realista, de corpo inteiro ou da cintura para cima, incluindo a cabeça, sem obstruções. Estes são requisitos publicados; não são garantias de anatomia ou preservação de identidade.

V3 acrescenta `elements`, com no máximo um elemento e apenas com `character_orientation="video"`:

```json
{
  "elements": [{
    "frontal_image_url": "https://imagem-frontal",
    "reference_image_urls": ["https://outro-angulo"]
  }]
}
```

O tipo `ElementInput` permite imagem frontal e zero a três imagens de outros ângulos. O provedor documenta referência `@Element1` no prompt. A existência desse campo não significa que toda versão do aplicativo ofereça seu upload ou que uma geração tenha preservado a identidade com sucesso.

**Controles não publicados nesse contrato:** FPS, resolução, seed, intensidade do movimento, peso de preservação facial, fidelidade corporal, CFG e duração explícita. Não envie esses campos supondo que serão atendidos. Cortar o vídeo de referência altera sua duração; converter FPS ou tamanho do resultado é pós-processamento e não cria detalhes ou frames inferidos adicionais. Sliders sem correspondência no motor não devem ser apresentados como controles de IA efetivos.

O schema não informa resolução nativa por plano, valores de cobrança nem SLA. Não foi possível verificar preços por causa do bloqueio de rede. Antes de uma geração paga, confira o preço vigente e os termos na conta fal. `standard` e `pro` são endpoints reais, mas não se deve inventar uma equivalência fixa entre nome do plano e resolução, velocidade ou ganho de qualidade.

## Fila, upload e resultado

O SDK Python oficial confirma:

1. Upload com `fal_client.AsyncClient(key=...).upload_file(path)`, que devolve uma URL.
2. `POST https://queue.fal.run/{endpoint}` com JSON de entrada e `Authorization: Key ...`.
3. A resposta devolve `request_id`, `status_url`, `response_url` e `cancel_url`.
4. Consultar `GET status_url?logs=true`. Os estados de inferência são `IN_QUEUE`, `IN_PROGRESS` e `COMPLETED`.
5. Ao concluir, obter `GET response_url`; o resultado do modelo tem `{"video":{"url":"...", ...}}`.
6. O cancelamento usa `PUT cancel_url` e é uma tentativa; não se deve prometer estorno nem interrupção de uma inferência já iniciada.

Use os URLs retornados pelo provedor e valide origem/esquema antes de requisitá-los. Ao reconstruir um handle pelo request ID, o próprio SDK usa a raiz da aplicação `fal-ai/kling-video/requests/{request_id}`, não necessariamente o endpoint completo de versão/modo. Conserve o ID remoto para retomada e evite duplicar cobranças após reinício ou timeout de submissão.

A implementação oficial consultada usa `https://rest.fal.ai/storage/auth/token?storage_type=fal-cdn-v3` e CDN `https://v3.fal.media`; não pressuponha o antigo `rest.alpha.fal.ai`. Existe fallback oficial para armazenamento GCS. Use o SDK para upload e restrinja a expiração quando a versão instalada oferecer `StorageSettings`; retenção padrão não significa exclusão imediata. Arquivos enviados e resultados podem ser processados e retidos por terceiros conforme seus termos. Excluir o arquivo local não comprova exclusão no provedor.

A configuração de rede precisa permitir pelo menos `queue.fal.run`, `rest.fal.ai` e o host de CDN realmente usado pela versão instalada. A página de documentação usa `fal.ai`. Hosts adicionais de armazenamento devem ser adicionados somente conforme a resposta real/documentação do serviço, preservando a política existente. Não contorne bloqueios de rede nem exponha a chave no frontend.

## Alternativa GPU aberta: Wan2.2-Animate-14B

O repositório oficial descreve animation como geração do personagem da imagem imitando o movimento do vídeo. Replacement também usa o cenário e a máscara do vídeo e tem outros requisitos de pré-processamento. Para o objetivo de preservar uma modelo digital, animation é o ponto de partida apropriado.

O pipeline oficial prepara `src_pose.mp4` e `src_face.mp4`; replacement também produz `src_bg.mp4` e `src_mask.mp4`. A preparação usa detector, estimador de pose de corpo/mãos/rosto e, opcionalmente, segmentação e edição de imagem. O guia identifica `yolov10m.onnx`, `vitpose_h_wholebody.onnx`, `sam2_hiera_large.pt` e `FLUX.1-Kontext-dev` como componentes. Esses checkpoints e suas licenças precisam de revisão individual.

Exemplo oficial de retargeting básico, sem o editor opcional FLUX:

```bash
python wan/modules/animate/preprocess/preprocess_data.py \
  --ckpt_path ./Wan2.2-Animate-14B/process_checkpoint \
  --video_path ./inputs/motion.mp4 \
  --refer_path ./inputs/character.jpg \
  --save_path ./prepared \
  --resolution_area 1280 720 \
  --retarget_flag

python generate.py --task animate-14B \
  --ckpt_dir ./Wan2.2-Animate-14B/ \
  --src_root_path ./prepared/ --refert_num 1
```

O guia alerta que retargeting básico exige a imagem e o primeiro frame em pose frontal estendida. Também alerta que o retargeting simplificado pode falhar, que diferenças de proporção causam deformações e que a máscara simplificada é para uma pessoa. `--use_flux` habilita uma edição adicional que também não garante consistência; não o habilite automaticamente sem licença apropriada para o uso pretendido.

A implementação oficial tem inferência GPU única e distribuída FSDP/Ulysses. Existe `diffusers.WanAnimatePipeline` com `image`, `pose_video`, `face_video`, `mode="animate"`, `segment_frame_length` e `prev_segment_conditioning_frames`. O snippet de README consultado contém um erro tipográfico de vírgula em `from_pretrained`; ao implementar, use a documentação da versão de Diffusers fixada e um teste real.

O modelo de 14 bilhões de parâmetros exige uma GPU CUDA e planejamento de VRAM, RAM e armazenamento. Não foi medido um mínimo de VRAM para Animate nesta máquina, que não expõe GPU NVIDIA. A menção a 80 GB em outra seção do README é para T2V-A14B e não deve ser tratada como um benchmark do Animate. Offload, dtype, atenção, resolução, duração e batch alteram memória e latência; valide no hardware alugado antes de aceitar tarefas ou anunciar limites. Uma máquina CPU sem GPU não valida a geração desse modelo.

O README e `LICENSE.txt` de Wan2.2 declaram Apache-2.0 para seus modelos. Isso não torna automaticamente Apache-2.0 todos os detectores, pesos auxiliares ou FLUX usados por pré-processamento. Revise licenças e termos de cada componente antes de redistribuir ou comercializar a pilha completa. A licença permissiva do SDK fal também não concede licença sobre Kling nem substitui os termos comerciais da API.

## Avaliação de qualidade e uso responsável

Nenhuma fonte consultada garante ausência de dedos deformados, flicker, troca de identidade ou roupas. Revisão humana continua necessária. Uma avaliação útil deve comparar entradas e saída de diversas pessoas fictícias adultas, movimentos simples e difíceis, oclusões, diferentes proporções, comprimentos e iluminação; registrar versões, parâmetros, duração, falhas e custos. Identidade, anatomia das mãos, fidelidade da pose e naturalidade exigem medidas especializadas e análise visual, além de verificações de arquivos.

Metadados, duração válida, decodificação, continuidade de frames e métricas simples de variação temporal ajudam a detectar problemas técnicos. Não comprovam identidade, idade, consentimento ou qualidade cinematográfica. Um detector de rosto também não é um verificador confiável de idade.

Use apenas personagens fictícios adultos ou mídias autorizadas dentro das políticas do serviço. Mantenha a moderação do provedor ativada, proteja uploads e disponibilize exclusão local. Uma declaração de autorização não comprova consentimento e não substitui avaliação de conteúdo. Não anuncie bloqueio infalível de menores ou de conteúdo íntimo não consensual. Conteúdo adulto explícito pode ser recusado pelo serviço; esta integração não promete suporte a ele nem oferece desativação de segurança.

## Fontes oficiais

- [Tipos oficiais fal: schema dos modelos, commit fixado](https://github.com/fal-ai/fal-js/blob/a29c8955d51c7e9009091b43dca4f10660f721ae/libs/client/src/types/endpoints.ts): `KlingVideoV3ProMotionControlInput`, `KlingVideoV26ProMotionControlInput`, `ElementInput`, `I2VOutput` e mapa de endpoints.
- [SDK Python oficial fal: fila, uploads e lifecycle](https://github.com/fal-ai/fal/blob/main/projects/fal_client/src/fal_client/client.py).
- [Documentação Kling v3 pro Motion Control](https://fal.ai/models/fal-ai/kling-video/v3/pro/motion-control/api) e [v2.6](https://fal.ai/models/fal-ai/kling-video/v2.6/pro/motion-control/api). As páginas estavam bloqueadas neste ambiente; não foram usadas para inventar preço ou capacidade.
- [Wan2.2 oficial: modelos, inferência e licença](https://github.com/Wan-Video/Wan2.2).
- [Wan Animate: guia oficial de pré-processamento](https://github.com/Wan-Video/Wan2.2/blob/main/wan/modules/animate/preprocess/UserGuider.md).
- [Licença Wan2.2](https://github.com/Wan-Video/Wan2.2/blob/main/LICENSE.txt).
- [Pesos Animate na organização oficial Wan-AI](https://huggingface.co/Wan-AI/Wan2.2-Animate-14B) e [pesos para Diffusers](https://huggingface.co/Wan-AI/Wan2.2-Animate-14B-Diffusers). Links indicados pelo README; pesos não baixados nem testados nesta pesquisa.
