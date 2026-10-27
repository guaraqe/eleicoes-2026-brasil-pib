# Votos ponderados pelo PIB — 2º turno presidencial, 25 de outubro de 2026

## Objetivo

Verificar a afirmação de que Lula teria tido só de 30% dos votos quando
ponderados pelo PIB. Usamos dados dos PIB estadual e municípal de 2023,
dividido entre os candidatos segundo os votos válidos, para mostrar que esta
afirmação é exagerada.

## Resultados

Dados baixados em 27 de outubro de 2026:

| Método | Lula | Flávio Bolsonaro |
| --- | ---: | ---: |
| PIB de cada estado inteiro para o vencedor | 26,77% | 73,23% |
| PIB estadual × fatia de votos no estado | 47,84% | 52,16% |
| PIB municipal × fatia de votos no município | 47,15% | 52,85% |
| ↳ só capitais (28,30% do PIB) | 51,73% | 48,27% |
| ↳ fora das capitais (71,70% do PIB) | 45,33% | 54,67% |

## Como executar

Requer apenas Python 3, sem dependências externas:

```sh
python3 analyze.py
```

A primeira execução baixa os resultados oficiais dos 5.571 municípios. As
execuções seguintes usam o cache em `data/`. Opções: `--refresh` apaga o cache e
baixa tudo de novo; `--workers N` define quantos downloads rodam em paralelo
(padrão 32).

Arquivos gerados:

- `results/summary.json`: os três métodos, os percentuais nacionais e a comparação capitais × demais áreas.
- `results/municipalities.csv`: PIB, votos e PIB atribuído a cada candidato, por município.
- `results/states.csv`: PIB e votos por estado (incluindo o DF).
- `data/`: respostas originais das fontes. Cada arquivo tem um `.source.json` com URL, horário do download (UTC) e SHA-256.

O script confere que:

- os votos municipais mais os do exterior batem com o total nacional oficial;
- os votos municipais batem com o resultado oficial de cada um dos 27 estados/DF;
- todo município tem PIB e votos;
- o PIB atribuído aos candidatos soma 100% do total.

Também rejeita resultados incompletos e arquivos de outra eleição ou de outro turno.

## Notas de método

- Votos brancos, nulos e abstenções não entram no cálculo.
- Os votos do exterior entram na conferência do total nacional, mas não na
  ponderação, porque não há PIB correspondente.
- Boa Esperança do Norte (MT) foi instalada em 2025 com partes de Sorriso e Nova
  Ubiratã. Os três municípios são somados em uma única área, com os votos de 2026
  e o PIB de 2023 de Sorriso e Nova Ubiratã. Por isso os 5.571 municípios viram
  5.569 áreas. Nenhum voto ou PIB fica de fora ou é contado duas vezes. Outras
  mudanças de fronteira entre municípios não são ajustadas.
- 2023 é o ano mais recente do PIB municipal do IBGE.

## Fontes

- TSE, resultados do 2º turno (`ele2026/6258`): [nacional](https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json), [códigos de municípios e capitais](https://resultados.tse.jus.br/oficial/ele2026/6258/config/mun-e006258-cm.json). Os arquivos de cada estado e município seguem o mesmo padrão de URL.
- IBGE, [SIDRA tabela 5938](https://sidra.ibge.gov.br/tabela/5938), variável 37 (PIB a preços correntes), 2023, em mil reais: [consulta exata](https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2023?formato=json).
- IBGE, [criação de Boa Esperança do Norte](https://educa.ibge.gov.br/criancas/voce-sabia/22741-novo-municipio.html).
