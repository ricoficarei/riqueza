# MAYCOM CHEF CONTROL — validação executada

Esta entrega foi validada em Linux x86-64, Python 3.12, Node.js 24, FFmpeg/FFprobe e Chromium. Nenhuma chave fal foi fornecida e nenhuma inferência paga foi executada.

| Verificação | Resultado observado |
| --- | --- |
| `bash setup.sh` | Instalação pelos lockfiles e build de produção concluídos. Reexecução também concluída. |
| `cd backend && .venv/bin/python -m pytest -q` | **46 testes passaram**. Um aviso de deprecação do TestClient/HTTPX, sem falha. |
| Contrato do provedor | 14 dos 46 testes verificam HTTP, segurança do modelo, parâmetros, cancelamento, validação de CDN, limites de download e proteção de credenciais. Respostas externas são dublês explícitos de teste. |
| Mídia local | FFmpeg e OpenCV executados com arquivos sintéticos de teste: upload, detecção por conteúdo, corte, extração do primeiro frame, exportação MP4, áudio e métricas visuais. |
| Fila e API | Revisão obrigatória, direitos, limites, autenticação por token/cookie, concorrência, recuperação sem reenvio automático, cancelamento e exclusão testados. |
| `npm run build` | TypeScript e Vite concluídos. |
| `bash start.sh` | Servidor iniciou; `/api/health` respondeu `status=ok`; frontend e APIs responderam. |
| `cd e2e && npm test` | Chromium passou: interface real, uploads de imagem/vídeo, mídia de entrada reproduzível, revisão bloqueada sem configuração, geração indisponível sem credencial, nova criação limpa a seleção, desktop/celular sem overflow e nenhum erro JavaScript. |
| Limpeza do browser | Arquivos enviados pelo teste foram excluídos. `/api/assets` e `/api/jobs` retornaram listas vazias. |
| Arquivos privados | Diretório de dados configurado com permissão 0700; uploads não são servidos como arquivos estáticos públicos. |

## O que esta validação não comprova

O adaptador real conecta Kling v3 e v2.6 Motion Control via fal. O contrato foi conferido em fontes oficiais e testado com respostas controladas; **não foi realizada uma geração na conta do provedor**. Portanto, não foi verificada disponibilidade comercial, latência, cobrança efetiva, qualidade visual, fidelidade corporal, mãos, rosto ou preservação de identidade de um vídeo gerado.

A revisão humana e a verificação do provedor não são garantia infalível de idade ou consentimento. Métricas de fluxo óptico, nitidez e luminância não são validação anatômica ou biométrica. Wan2.2-Animate foi pesquisado, mas não foi integrado nem executado. Não há GPU NVIDIA disponível nesta instância.

## Passo externo para validar uma geração

Configure uma conta fal habilitada com créditos e `FAL_KEY` no servidor. Libere os domínios necessários na política da hospedagem. Configure os tokens privados de acesso/revisão do estúdio, reinicie o processo e use arquivos autorizados de adultos com personagem fictícia adulta em cena não íntima. A geração pode consumir créditos. Valide o MP4 e faça revisão visual conforme `QUALITY.md` antes de considerar os critérios cinematográficos atendidos.

O rascunho do ambiente recebeu instruções de instalação/inicialização, requisitos de variáveis e destinos de rede. Salvar esse rascunho não aplica credenciais, não publica o serviço e não comprova restauração em uma nova tarefa. Revise e salve as configurações do ambiente; a publicação pelo produto permanece uma etapa separada.


## Versão portátil Windows

Foi compilado um backend Windows x64 com Python, dependências, frontend e FFmpeg/FFprobe incluídos. O executável congelado, sem consultar os fontes do projeto, passou **20 verificações reais no Wine**, registradas em `windows-package-validation.json`: abertura privada, sessão, configuração da conexão, uploads, análise OpenCV/FFprobe, mídia FFmpeg, revisão, preview e exclusão. Não houve chamada paga.

No Wine, a criptografia de conta Windows (DPAPI) estava indisponível. O teste verificou o fallback seguro: a chave fica somente em memória, sem ser gravada em texto aberto. O aplicativo explica essa condição na tela. A persistência DPAPI e o funcionamento em Windows 10/11 físico ainda precisam de validação nesse sistema.

A janela Electron inclui seu próprio Chromium; o usuário final não instala Python, Node, FFmpeg ou navegador adicional. O pacote portátil contém avisos e licenças dos componentes. Os comandos de desenvolvimento deste repositório não são necessários para abrir o `.exe`.


O arquivo portátil Electron final foi gerado com sucesso: `MAYCOM-CHEF-CONTROL-Portable-1.0.0-x64.exe`, 226.261.990 bytes. Os 3 testes de segurança do shell passaram. O teste da janela Electron no Wine foi inconclusivo; o host também não executa o componente ELF32 necessário ao bootstrap NSIS, apesar da imagem Wine32 instalada. Isso não confirma um defeito do aplicativo, mas a abertura de ponta a ponta com dois cliques e a interface em Windows 10/11 real permanecem pendentes de teste. Nenhuma opção de segurança da versão distribuída foi desativada.

SHA256 do arquivo final: `c85e276974f632729e4c2d1e5c1b9fd27dec7710b95c0faf57affb96fbe6ab6f`.

A sessão não oferece ferramenta de anexo/upload de binários. Links de editor não foram tratados como download validado. O envio para uma versão rascunho GitHub ainda não foi executado: a política de rede atual bloqueia `api.github.com` e `uploads.github.com`; os destinos foram preparados no rascunho de configuração para revisão do usuário. Não existe URL de release publicada nesta entrega.
