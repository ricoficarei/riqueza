# MAYCOM CHEF CONTROL — launcher empacotado

O produto distribuído usa uma janela Electron com Chromium incluído e um backend
Windows empacotado como `MaycomBackend.exe`. Não exige Python, Node.js, FFmpeg ou
um navegador instalado separadamente no computador de destino.

## Contrato com o shell

O shell inicia `resources/backend/MaycomBackend.exe --server` com stdin/stdout
conectados por pipes e `windowsHide: true`. O backend:

1. Prepara os executáveis de mídia incluídos no pacote e os arquivos de dados.
2. Abre apenas uma porta dinâmica em `127.0.0.1`.
3. Aguarda `/api/health` responder, sem tratar um PID como sinal de prontidão.
4. Escreve uma única linha JSON em stdout:

   ```json
   {"url":"http://127.0.0.1:PORT/desktop/start/NONCE","pid":1234}
   ```

5. O shell carrega esse URL de uso único. O servidor cria a sessão HttpOnly e
   redireciona para a interface, sem expor o token de acesso à aplicação web.
6. Fechar stdin solicita o encerramento. O shell deve permitir alguns segundos
   para a fila gravar seu estado antes de terminar o processo à força.

Logs não são enviados a stdout. Ficam em stderr e em `desktop.log`, dentro da
pasta privada de dados. O acesso HTTP não registra o URL de bootstrap.

## Recursos incluídos

No bundle PyInstaller, o launcher espera:

```text
frontend/dist/index.html
frontend/dist/assets/...
bin/ffmpeg.exe
bin/ffprobe.exe
```

O diretório de dados normal é `%LOCALAPPDATA%\MAYCOMCHEFCONTROL`. A configuração
do provedor usa `settings.dat`, protegido pelo backend com Windows DPAPI para o
usuário atual. Se esse serviço do Windows estiver indisponível, a chave fica
somente na memória da sessão e a interface informa a limitação; não há fallback
para salvar a chave em texto simples no Windows. Os tokens de sessão/revisão são gerados a cada processo e não
precisam ser digitados pelo usuário. A primeira configuração da chave fal é
feita na interface local do aplicativo. Créditos e conexão com o serviço
externo continuam necessários para gerar vídeos.

## Validação do pacote

```text
MaycomBackend.exe --self-test CAMINHO_INEDITO_PARA_RELATORIO.json
```

Esse teste usa um perfil descartável, abre a API com autenticação, verifica o
bootstrap de uso único e os arquivos da interface incluídos. Salva e remove uma
chave deliberadamente inválida apenas no perfil de teste, verificando proteção
DPAPI no Windows; se DPAPI estiver indisponível, verifica explicitamente o modo
somente em memória e registra a persistência como não validada. Não solicita
inferência enquanto a chave de teste está configurada. Cria
PNG e MP4 sintéticos com Pillow/FFmpeg, valida upload, FFprobe/OpenCV, revisão,
preview e exclusão. Confirma que a ausência de credencial não cria um vídeo de
geração. O JSON informa `passed` e os checks efetivamente executados.

O backend deve ser empacotado com subsistema console para fornecer o protocolo
JSON. O Electron oculta essa janela; não use o bootloader PyInstaller
`--windowed` para `MaycomBackend.exe`.
