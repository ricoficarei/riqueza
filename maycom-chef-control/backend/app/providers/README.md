# MAYCOM CHEF CONTROL: provedor de Motion Control

`FalMotionProvider` usa inferência real da fal.ai. Endpoints verificados no SDK
oficial: `fal-ai/kling-video/{v3|v2.6}/{standard|pro}/motion-control`. Padrão:
`v3/pro`. Integração requer `FAL_KEY`, créditos fal e rede disponível; os testes
de contrato usam HTTP simulado e não demonstram qualidade de geração real.

Dependências: `httpx` e `fal-client==1.0.3`. O SDK oficial envia os arquivos ao
armazenamento fal, com expiração solicitada de um dia. O aplicativo deve informar
essa transferência externa ao usuário. Exclusão local não comprova exclusão
imediata de arquivos, resultados ou logs no provedor; consulte sua retenção.

Parâmetros encaminhados: `image_url`, `video_url`, `character_orientation`,
`keep_original_sound`, `prompt` e `enable_safety_checker=true` obrigatório.
`model_version` e `quality` selecionam o endpoint. Nenhum controle fictício de
intensidade, preservação facial, FPS ou resolução é enviado. O provedor aceita
imagem da personagem; a extração de um frame de vídeo pertence à camada de mídia.
Não se anuncia condicionamento por vídeo inteiro da personagem. A extensão v3
`elements` para referências faciais adicionais ainda não está exposta.

Orientação `image` permite referência até 10 segundos; `video`, até 30 segundos.
Validar duração, dimensões e decodificação dos arquivos antes de submeter. Os
filtros do provedor não equivalem a uma garantia de idade ou consentimento.

`submit` devolve ID durável; `status`, `result` e `cancel` usam a rota de requests
oficial. Não há porcentagem de progresso inventada. A submissão paga não é
repetida automaticamente quando a resposta se perde. O cancelamento é pedido
ao provedor e não garante interrupção instantânea nem estorno.

`download_result` aceita HTTPS em `fal.media` e subdomínios, valida cada
redirecionamento antes de seguir, impõe 512 MiB, verifica contêiner MP4 e remove
arquivos parciais. Nenhuma chave fal é enviada ao CDN. A camada de mídia deve
fazer `ffprobe`/decodificação após o download para validar a mídia completa.

Testes de protocolo:

```sh
cd maycom-chef-control/backend
python -m pytest app/providers/tests -q
```

Fontes: cliente oficial [fal Python](https://github.com/fal-ai/fal/tree/main/projects/fal_client)
e tipos oficiais [fal JS](https://github.com/fal-ai/fal-js/blob/a29c8955d51c7e9009091b43dca4f10660f721ae/libs/client/src/types/endpoints.ts).
