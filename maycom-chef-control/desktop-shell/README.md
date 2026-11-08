# MAYCOM CHEF CONTROL — janela portátil Windows

O shell inclui o Chromium do Electron e inicia o backend empacotado. O usuário não precisa instalar Python, Node.js, FFmpeg, WebView2 ou um navegador separado. O arquivo portátil é aberto com dois cliques. A geração usa ComfyUI local e modelos instalados separadamente, sem conta ou créditos de API. A rota RX 6600/DirectML é experimental e não teve geração validada neste ambiente. Consulte `docs/LOCAL-GRATUITO.md`.

## Build de desenvolvimento

Execute no Linux com Node.js 22+ e acesso aos registros oficiais:

```bash
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci
MAYCOM_BACKEND_DIR=/caminho/da/pasta/MaycomBackend MAYCOM_LICENSES_DIR=/caminho/das/licencas npm run build:windows
```

`MAYCOM_BACKEND_DIR` deve conter o backend Windows real `MaycomBackend.exe` e todos os arquivos da distribuição PyInstaller. O build copia a pasta inteira para `resources/backend`. `MAYCOM_WINDOWS_OUTPUT` permite escolher a pasta de saída. O script recusa um executável ausente ou um arquivo que não seja um PE Windows empacotado.

`MAYCOM_LICENSES_DIR` deve conter os avisos de redistribuição: `PYTHON-LICENSE.txt`, `FFMPEG-LICENSE.txt`, `THIRD-PARTY-NOTICES.md`, as licenças dos pacotes Python e o código-fonte correspondente ao FFmpeg distribuído. A pasta inteira acompanha o aplicativo em `resources/licenses`. O guia `desktop/LEIA-ME-WINDOWS.txt` também acompanha o executável em `resources/LEIA-ME.txt`. O build recusa a ausência dos avisos principais.

Electron 45.2.3 e electron-builder 26.18.0 estão fixados. O download do Electron usa as verificações oficiais de integridade; o build não desativa TLS ou checksums. `signAndEditExecutable:false` evita alterar o bootloader oficial durante o cross-build Linux. A distribuição portátil não tem um certificado de assinatura de código próprio da marca.

## Contrato do backend

`MaycomBackend.exe --server` escreve uma linha JSON em stdout após iniciar:

```json
{"url":"http://127.0.0.1:49152/desktop/start/NONCE_ALEATORIO_DE_USO_UNICO","pid":123}
```

O shell aceita apenas `127.0.0.1`, porta não privilegiada e caminho de bootstrap restrito. Não aceita URLs arbitrárias ou PID do handshake como alvo de encerramento. Fechar stdin deve encerrar o backend de forma limpa; após cinco segundos, o shell encerra somente a árvore do processo que ele criou.

O renderizador não tem Node.js nem bridge IPC exposta, usa sandbox/context isolation e só acessa o servidor local. Permissões de câmera, microfone e dispositivos são negadas. Links externos são bloqueados; a única exceção é documentação HTTPS em `fal.ai` e `docs.fal.ai`, aberta no navegador do sistema somente quando o usuário clica. Esses links não são necessários para executar o aplicativo. Downloads MP4 abrem o diálogo nativo para salvar.

`npm test` valida o contrato de origem/bootstrap e as regras de navegação. `--smoke-test C:\pasta\relatorio.json` no aplicativo empacotado abre a janela, verifica a API e os dois campos de upload, grava relatório e screenshot, e encerra. O relatório deve ser inexistente. Esse teste não chama inferência paga.
