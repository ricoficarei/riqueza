# Componentes da versão portátil

O aplicativo reúne componentes independentes; seus avisos e licenças não são substituídos pelo nome MAYCOM CHEF CONTROL.

- **Electron e Chromium**: distribuição oficial Electron 45.2.3. Os arquivos `LICENSE` e `LICENSES.chromium.html` da distribuição acompanham o runtime. Fonte: https://github.com/electron/electron/tree/v45.2.3 .
- **CPython**: distribuição oficial Python Software Foundation 3.12.10, obtida do pacote NuGet `python` e conferida com o SHA-512 do catálogo. Licença PSF: https://github.com/python/cpython/blob/v3.12.10/LICENSE .
- **FFmpeg/FFprobe**: programas externos separados, build BtbN Windows GPL shared, revisão FFmpeg `5d85b7bfb2b024fd367ae3a938b4ac46a39e3a26`. A licença GPLv3 acompanha os binários em `licenses/ffmpeg/LICENSE.txt`. As bibliotecas adjacentes são incluídas sem modificações. Fonte correspondente FFmpeg: https://github.com/FFmpeg/FFmpeg/tree/5d85b7bfb2b024fd367ae3a938b4ac46a39e3a26 . Receitas e referências das dependências: https://github.com/BtbN/FFmpeg-Builds/tree/c63bb308a1de656b425c132a8102f8fd5389afc5 .
- **NumPy, OpenCV, Pillow, FastAPI, Starlette, Uvicorn, Pydantic, httpx, fal-client e dependências**: versões de build registradas no lockfile e nos manifests de compilação. As licenças de cada pacote permanecem aplicáveis. Código do SDK fal: https://github.com/fal-ai/fal/tree/main/projects/fal_client .
- **React, Vite, TypeScript e lucide-react**: usados para a interface e compilação. Versões fixadas em `frontend/package-lock.json`.

O adaptador fal é código cliente; o aplicativo não distribui pesos Kling nem concede direitos sobre esses modelos. Seus termos, créditos e retenção de arquivos são administrados pelo provedor.

A pasta de ferramentas da compilação guarda checksums, proveniência, fontes FFmpeg e receitas BtbN. Antes de redistribuir uma build diferente, mantenha os avisos, confira as licenças de todas as dependências e disponibilize o código correspondente exigido pelas licenças aplicáveis; não trate as receitas como se contivessem automaticamente todos os fontes de terceiros.
