# MAYCOM CHEF CONTROL — qualidade e validação

O objetivo é preservar a personagem e reproduzir o movimento com naturalidade. A versão entregue implementa preparação real de arquivos, integração de inferência e diagnósticos técnicos. Ainda não há evidência de geração paga bem-sucedida ou benchmark visual nesta máquina. Esta página distingue as verificações presentes do plano que precisa ser executado com credenciais, créditos, rede e entradas autorizadas.

## O que o software verifica

| Etapa | Verificação existente | O que não demonstra |
| --- | --- | --- |
| Upload | Formato decodificável, tamanho, pixels/dimensões, duração, FPS e áudio | Pessoa detectada, idade, consentimento ou pose correta |
| Preparação | Imagem de identidade, primeiro frame de vídeo da personagem, corte real da referência | Preservação da identidade pelo modelo |
| Inferência | Contrato de upload/fila/status/resultado do fal | Resultado visual quando testado somente com respostas simuladas |
| Exportação | MP4, duração/dimensões/FPS válidos e conversão real de vídeo | Detalhes adicionais, interpolação neural ou ausência de artefatos |
| Análise visual | Amostragem, fluxo óptico, luminância, nitidez e mudanças de histograma | Anatomia correta, mãos perfeitas, roupas estáveis ou rosto consistente |

O provedor faz a transferência de movimento a partir da referência. O backend local não executa DensePose, SMPL-X, retargeting de esqueleto, estimativa facial ou um verificador biométrico de identidade. **Fluxo óptico não é pose humana:** ele mede deslocamentos de pixels e inclui movimentos de câmera, fundo e compressão.

## Métricas locais

OpenCV amostra uniformemente até 48 frames e reduz cada amostra a no máximo 320 pixels no maior lado. A análise registra:

- Magnitude média de movimento por Farneback, em pixels por intervalo de amostra na resolução de análise.
- Diferença média normalizada entre imagens amostradas.
- Luminância média e maior salto normalizado entre amostras.
- Variação de histograma para sinalizar possíveis cortes.
- Nitidez aproximada pela variância do Laplaciano.

No relatório atual, saltos de luminância acima de 0,20 geram aviso; variação de histograma acima de 0,55 combinada com diferença de imagem acima de 0,20 pode contar como corte; nitidez média abaixo de 20 gera aviso. São heurísticas operacionais, não limites validados em estudos perceptuais. Movimentos rápidos, fundos uniformes, mudança legítima de luz ou cortes de edição podem gerar avisos sem defeito de geração. Artefatos curtos podem passar entre as amostras.

O relatório de saída usa `status="review_required"`. Checagens técnicas individuais podem ser `passed` enquanto identidade e anatomia continuam exigindo revisão. `automatic_corrections` permanece vazio: esta versão não aplica restauração de rosto, correção de mãos, estabilização neural ou reparo de roupas. Não apresente ausência de aviso como certificado de naturalidade.

O FPS escolhido é pós-processamento FFmpeg. Converter para 30 FPS pode repetir ou descartar frames; não cria novos estados anatômicos inferidos. Resolução e qualidade nativas dependem do endpoint contratado, e não foram certificadas nesta entrega.

## Testes de software

```bash
cd backend
.venv/bin/python -m pytest
cd ../frontend
npm run build
```

As suítes devem verificar uploads válidos/inválidos, revisão obrigatória, ausência de credenciais, autorização, persistência da fila, recuperação sem ressubmissão paga, cancelamento, tratamento de falhas, mídia gerada localmente para exercitar FFmpeg e contrato HTTP com respostas de teste. Fixtures sintéticas de teste não podem aparecer como resultados de geração no produto.

O build verifica TypeScript e gera os arquivos de produção. A validação por navegador deve exercitar upload, revisão, estados vazios, ausência do provedor, erros, preview e download. O relatório final de entrega deve informar os testes realmente executados e seus resultados; a existência deste plano não os transforma em testes aprovados.

## Teste de inferência real

Este procedimento ainda precisa de uma conta fal utilizável e créditos. Não existe fallback que produza um vídeo fictício quando a API estiver indisponível.

1. Inicie o backend com `FAL_KEY` e `MAYCOM_REVIEW_TOKEN`; mantenha o token de acesso se o estúdio estiver exposto remotamente.
2. Use uma imagem autorizada de personagem adulta fictícia e um vídeo de referência com uma pessoa adulta, corpo visível, sem cortes ou obstruções. Comece com um trecho de cinco segundos e um movimento simples.
3. Faça a revisão humana de ambas as entradas, aprove e gere em Kling v3/pro. Registre versão do aplicativo, endpoint, orientação, parâmetros, dimensões/duração das entradas e data.
4. Confira que o ID remoto aparece na operação do provedor e que um arquivo novo foi retornado. Valide no estúdio a reprodução completa, áudio quando solicitado, relatório e download MP4. Não confunda status `COMPLETED` remoto com qualidade aceita.
5. Assista à saída em velocidade normal e quadro a quadro nos trechos difíceis. Compare com imagem e referência. Registre falhas com timestamps.
6. Exclua tarefa e arquivos locais ao terminar. Confira a retenção no fal separadamente; TTL solicitado de um dia não garante exclusão imediata de toda cópia externa.

Erros de chave, créditos, rede, moderação ou entradas devem aparecer como erro, sem geração substituta. Em falha de submissão com resposta perdida, consulte o painel fal antes de reenviar para evitar cobrança duplicada. Cancelamento deve ser avaliado sem pressupor estorno.

## Bateria de naturalidade proposta

Esta bateria **não foi executada nesta entrega**. Use somente mídia autorizada e pessoas adultas; a personagem de destino deve ser fictícia adulta. A pesquisa comparativa precisa de orçamento, conjunto de entradas definido e avaliadores humanos.

| Dimensão | Casos propostos | Revisão necessária |
| --- | --- | --- |
| Rosto/identidade | Frente, perfil, giro de cabeça, oclusão breve, expressões | Forma do rosto, olhos, boca, cabelos e recuperação após oclusão |
| Corpo/proporções | Corpos e alturas diferentes, planos inteiro e médio, giros | Comprimento dos membros, articulações, silhueta e estabilidade entre frames |
| Movimento | Caminhada, dança lenta/rápida, gestos, agachamento e giro | Pose reproduzida, ritmo, contato com o solo e transições |
| Mãos | Mãos próximas do rosto, cruzadas, gestos finos, oclusão | Número/forma dos dedos, aderência ao objeto e continuidade |
| Roupa/cabelo | Texturas, acessórios e cabelo em movimento | Trocas de peça, desaparecimentos, textura e vazamento para o fundo |
| Luz/câmera | Luz estável, mudanças de luz, câmera estática e móvel | Sombras coerentes, flicker e separação entre movimento do corpo/câmera |
| Duração | 3, 5, 10 e 30 segundos quando o modo permitir | Deriva acumulada, continuidade no final e sincronismo de áudio |
| Enquadramento | Retrato/paisagem, corpo inteiro/médio e bordas do quadro | Cortes indesejados, deformações fora de campo e preservação da composição |

Para comparação de motores, use as mesmas entradas e orientações válidas, registre endpoint e custo real, mantenha as falhas no denominador e não selecione apenas melhores resultados. Repita casos porque a inferência é estocástica e esse contrato não expõe seed. Avaliadores devem registrar por critério se o resultado foi aceito, rejeitado ou inconclusivo, com evidência visual e timestamps. Não produza uma nota global de “identidade” a partir de métricas simples de brilho ou nitidez.

Uma versão futura pode avaliar keypoints e proporções, sincronismo temporal e embeddings de identidade com modelos adequados e licenças revisadas. Essas verificações não estão implementadas e também precisam de validação para não confundirem iluminação, expressão ou oclusão com troca de identidade.

## Critérios que permanecem pendentes

São pendentes a geração real com a conta configurada, a revisão de identidade/naturalidade nos vídeos obtidos, a bateria diversa acima e qualquer alegação comparativa com outros serviços. A opção Wan2.2-Animate-14B foi estudada, sem instalação de pesos ou inferência GPU validada. A publicação pública, a operação multiusuário e a garantia de detecção de idade/consentimento não fazem parte das capacidades verificadas.

As escolhas e fontes técnicas estão em [Modelos](MODELS.md); o caminho dos dados e as limitações de implantação estão em [Arquitetura](ARCHITECTURE.md).
