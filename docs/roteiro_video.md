# Roteiro de vídeo — 5 minutos
## Harmonized Burning Activity Calendar (MODIS + VIIRS)

Formato sugerido: gravação de tela do app com narração, abrindo e fechando com a câmera ligada.
Ritmo: cerca de 140 palavras por minuto. O texto de fala abaixo tem ~720 palavras, o que dá 5 minutos com pausas curtas.
Antes de gravar: deixe o backend e o frontend rodando, abra http://localhost:5173 em tela cheia, região "South America", ano 2024, modo "Activity".

---

### 0:00 – 0:30 · Abertura (câmera ou slide com o título)

**Na tela:** título do projeto e o nome da equipe.

**Fala:**
> Quase metade das emergências que a CONAE acompanha são incêndios. Para saber se um ano está fora do normal, os gestores usam um calendário de atividade de fogo construído com focos de calor de satélite. O problema: esse calendário está prestes a quebrar. O MODIS, que registra focos desde 2002, está saindo de operação, e o VIIRS, que o substitui, enxerga o fogo de um jeito diferente. Nosso projeto junta os dois numa única série contínua, de 2002 até hoje, e entrega isso num aplicativo web.

---

### 0:30 – 1:15 · O problema em números

**Na tela:** figura `reports/figs/ratio_by_month.png` (razão VIIRS/MODIS por mês em Brasil, Argentina, Bolívia e Paraguai).

**Fala:**
> Por que não dá simplesmente somar os dois? Nós medimos. No mesmo lugar e no mesmo dia, o VIIRS detecta entre duas e meia e quatro vezes mais focos que o MODIS. E essa razão não é constante: muda com a estação e com a região, porque o pixel do VIIRS tem 375 metros e o do MODIS tem 1 quilômetro. Em meses de poucos fogos pequenos, a diferença cresce. Um fator único de conversão, portanto, erraria o calendário justamente nos meses em que ele mais importa.

---

### 1:15 – 2:30 · O método

**Na tela:** figura `reports/figs/overlap_monthly.png` e, em seguida, a tabela de modelos em `reports/validation.md`.

**Fala:**
> Usamos os arquivos do FIRMS da NASA: 19 anos de MODIS e 8 anos de VIIRS NOAA-20, 34 milhões de detecções em 14 países da América do Sul.
>
> Primeiro, colocamos os dois sensores numa grade comum de 0,1 grau por dia. Depois, usamos a janela em que os dois voam juntos, de abril de 2018 a dezembro de 2020, para aprender como converter VIIRS em "equivalente MODIS". A conversão é um fator ajustado por bloco de 2 graus e por mês do ano, com encolhimento estatístico para que regiões com poucos dados herdem o valor continental.
>
> O ponto central é que não escolhemos o modelo por intuição. Comparamos nove variantes e também modelos não lineares, sempre com validação cruzada: ajustamos em dois anos e testamos no terceiro, que o modelo nunca viu. O vencedor acerta 80% da variância célula a célula e 99% no nível país-mês, sem viés. E dois resultados honestos: colapsar os pixels do VIIRS em 1 quilômetro não melhorou nada, e os modelos não lineares foram piores. A conversão linear regional é simples e é a melhor.
>
> Escolhemos converter VIIRS para unidades MODIS, e não o contrário, porque a história de 19 anos é MODIS e um foco que o MODIS nunca detectou não pode ser inventado. O detalhe do VIIRS continua disponível nas colunas brutas.

---

### 2:30 – 4:15 · Demonstração do aplicativo

**Passo 1 (2:30) — Na tela:** o app com "South America", 2024. Passe o mouse sobre algumas células do calendário anos × meses.

**Fala:**
> Este é o calendário harmonizado. Cada linha é um ano, cada coluna um mês, de 2002 a 2025. Em azul na legenda, os anos observados pelo MODIS; em laranja, os anos VIIRS já convertidos. A transição é invisível: 2024 aparece como o terceiro ano mais ativo da série, 36% acima da média histórica, com pico em setembro.

**Passo 2 (2:55) — Na tela:** clique em "Anomaly".

**Fala:**
> No modo anomalia, cada mês é comparado com a climatologia de 2002 a 2020. Azul é abaixo do normal, laranja acima. É aqui que o gestor enxerga tendência e padrão sazonal de uma vez.

**Passo 3 (3:15) — Na tela:** selecione "Argentina" e o ano 2020. Role até o gráfico "Annual totals".

**Fala:**
> Trocamos para a Argentina. 2020 foi o ano recorde da série, o ano dos incêndios do Delta do Paraná e de Córdoba. Nos anos de sobreposição, 2018 a 2020, o gráfico mostra o VIIRS convertido como um ponto sobre a barra do MODIS observado: a validação fica visível para o usuário, e os anos VIIRS trazem a barra de incerteza da validação cruzada.

**Passo 4 (3:40) — Na tela:** clique em "Draw area on map" e desenhe um retângulo sobre a região central da Argentina. Mostre o calendário diário e o ciclo sazonal atualizando.

**Fala:**
> O usuário não fica preso a fronteiras. Desenhando qualquer área no mapa, todos os painéis recalculam em menos de um segundo: o calendário dia a dia, o ciclo sazonal contra a climatologia e o mapa de onde queimou.

**Passo 5 (4:00) — Na tela:** clique em "Daily series" para baixar o CSV; abra o painel "Method & validation".

**Fala:**
> Tudo pode ser baixado em CSV, com os valores harmonizados, as contagens brutas de cada sensor e a fonte de cada dia. E o método está dentro do próprio app, com a tabela de validação de todos os modelos testados.

---

### 4:15 – 4:45 · Limites e próximos passos

**Na tela:** figura `reports/figs/cellmonth_scatter.png` ou volte ao calendário.

**Fala:**
> Somos transparentes sobre os limites. A calibração usa dois anos e nove meses de sobreposição; com o VIIRS Suomi-NPP, disponível desde 2012, e com o MODIS de 2021 em diante, a mesma pipeline alongaria essa janela para mais de dez anos. Os fatores são regionais, então mudanças muito locais no tamanho dos fogos não são capturadas. E a pipeline é genérica: basta trocar a lista de países para rodar em qualquer região do planeta.

---

### 4:45 – 5:00 · Encerramento (câmera)

**Fala:**
> Quando o MODIS se apagar, o calendário de fogo não precisa se apagar junto. Entregamos uma série contínua de 2002 a 2025, validada, com incerteza declarada, e uma ferramenta que qualquer gestor de emergência pode usar hoje. Obrigado.

---

## Números para ter à mão (caso perguntem)

| Item | Valor |
|---|---|
| Período coberto | 2002-01-01 a 2025-12-31 |
| Detecções processadas | 13,6 milhões MODIS + 20,6 milhões VIIRS |
| Países | 14 (América do Sul) |
| Janela de calibração | 2018-04-01 a 2020-12-31 |
| Grade | 0,1° × dia |
| Modelo escolhido | fator linear por bloco 2° × mês (`block_month_n`) |
| Fator continental | 0,257 focos MODIS por pixel VIIRS (≈ 1 para 3,9) |
| R² célula × mês (ano não visto) | 0,80 |
| R² país × mês | 0,99, erro relativo 26% |
| Viés total | 0,1% |
| América do Sul 2024 | 976 mil focos equivalentes, 3º da série, +36% vs média |
| Tempo de resposta da API | < 0,1 s por consulta |

## Dicas de gravação

- Grave a tela em 1920×1080 com o navegador em tela cheia; a barra lateral e os quatro cartões cabem sem rolagem.
- Faça o passo 4 (desenhar área) uma vez antes de gravar para pegar o jeito: clique em "Draw area on map", arraste, solte.
- Se faltar tempo, corte o passo 5 da demonstração; o download pode ser só citado.
- Se sobrar tempo, mostre o tooltip de um mês de 2019 no calendário: ele exibe lado a lado o MODIS observado e o VIIRS harmonizado.
