# Diagnostic des durées : pourquoi 4084 s, puis 157 s, puis 343 s ?

Date : 2026-09-20. **Aucune modification du code ni de l'architecture** : les instruments sont posés de l'extérieur (enveloppes sur `shutil.copytree`, `subprocess.run`, `generate`, `verify`) et ne sont pas
dans le dépôt de code. Ce dossier contient les instruments (`diag_*.py`, `bench_*.py`) et les mesures brutes (`mesures/`), pour rejouer le diagnostic.

## Conclusion

| Durée observée | Explication démontrée |
|---|---|
| **4 084 s** (142 tests, étape 12) | **La machine était en veille pendant 3 844 s.** Journal Windows : veille à 17:28:03,5 UTC, réveil à 18:32:07,9 UTC (source : bouton d'alimentation), à l'intérieur de la passe lancée à 17:25:48 et terminée à 18:34:09. Fenêtre de 4 101 s = **3 844,4 s de veille + 256,6 s d'exécution réelle** ; pour la seule étape de tests : 4 084,5 − 3 844,4 = **240 s**. Le chronomètre d'`unittest` (`time.perf_counter`) **compte le temps de veille** (la documentation Python le précise, et cette passe le prouve). |
| **157 s** (144 tests, étape 13) | Bas de la plage normale de cette machine. |
| **343 s** (204 tests, étape 14) | 60 tests de plus (`test_ap_gaps` 38, `test_ap_gate` 22), dont 38 injections : 55 à 124 s mesurés (moyenne 92 s) pour `test_ap_gaps` et 20 s pour `test_ap_gate`. 157 s + ~111 s ≈ 268 s ; 343 s reste dans la plage mesurée. |

Ce n'est **pas** PostgreSQL : le test PostgreSQL dure 28 à 68 s sur 3 passes (6 à 16 % de la suite selon la passe), toutes ses expériences sont confirmées, et son cas le plus lent est le démarrage à froid du serveur (initdb), pas les transactions. Ce n'est pas non plus une régression du code : trois passes sans modification, 204 / 204 tests verts à chaque fois, aucun échec.

**Le 4084 s est donc une anomalie ponctuelle, établie par le journal d'alimentation. Les 157 s et 343 s appartiennent à la plage normale de cette machine**, qui est très large : les 144 mêmes tests de l'étape 13 ont pris **212 s, 278 s et 424 s** sur les trois passes contrôlées (facteur 2), contre 157 s le jour de l'étape 13.

## Pourquoi la plage normale est-elle si large ?

1. **La suite est dominée par les tests d'injection** : 108 tests sur 204, soit **76 à 88 % du temps** (255 à 435 s sur 329 à 497 s). Chacun copie 362 fichiers du dépôt, réimporte le paquet depuis un répertoire neuf et relance la vérification : 2,4 à 4,0 s par test, dont 0,6 à 1,2 s de copie. Sur une machine calme, une copie prend 0,68 s (0,51 à 1,15 s sur 60 copies mesurées).
2. **La machine est saturée par ailleurs** : Core m3-8100Y (2 cœurs, 1,1 GHz), **4 Go de RAM dont 210 à 440 Mo libres, 6,5 Go de fichier d'échange en usage**, Chrome consommant plus d'un cœur (5 processus, ~1,1 Go), application Claude, Defender actif (son temps CPU n'est pas mesurable sans droits administrateur). Une charge de calcul **strictement identique**, répétée 8 fois, a pris **de 1,9 s à 13,7 s** (écart de 227 %) pour 1,3 à 3,7 s de CPU réellement consommé : dans les essais lents, le processus n'obtenait pas le processeur.
3. **47 à 60 % du temps de la suite n'est pas du CPU du processus** : attente d'entrées-sorties, de mémoire (pagination) et du processeur lui-même.
4. **Des à-coups isolés** : dans la passe A, un seul test a coûté 52 s contre 3 s en moyenne (+49 s sur un excès total de 122 s) ; les excès sont des pics, pas un démarrage à froid (les 30 premiers tests n'y contribuent que 0,2 s).

## Ce que ce diagnostic n'a pas montré

- Le rôle de Defender : non mesurable sans droits administrateur (exclusions illisibles, temps CPU de `MsMpEng` inaccessible).
- L'effet de la thermique : la fréquence relevée est restée à 1 105 MHz pour un maximum de 1 608 MHz, sans variation, donc rien ne permet de l'incriminer ni de l'écarter.
- Trois passes ne suffisent pas à définir un seuil : elles montrent la plage, pas sa distribution.

## Recommandations (rien n'a été appliqué)

1. **Ne plus lire un `Ran N tests in X s` isolé** : sur cette machine, une veille suffit à le fausser de plus d'une heure. Consigner aussi le temps CPU et la date de début/fin, et comparer sur plusieurs passes.
2. **Réduire le coût d'une injection** (levier principal) : copier une fois par session et restaurer, ne copier que le sous-arbre concerné, ou précompiler ; à décider séparément, jamais dans le cadre d'un diagnostic.
3. **PostgreSQL** : réutiliser un modèle de grappe déjà initialisé (le démarrage à froid coûte 14 à 43 s, à chaud 0,6 à 1,1 s).
4. **Environnement** : fermer le navigateur pendant les passes complètes, ajouter des exclusions Defender pour le dépôt et le répertoire temporaire (droits administrateur), ou davantage de mémoire.

# Mesures

## Niveau 1 : global

|                                                      |        A |        B |        C |
|------------------------------------------------------|----------|----------|----------|
| durée totale de la passe (s)                         |    774.6 |    857.8 |    676.9 |
|   dont veille de la machine chevauchant la passe (s) |      0.0 |      0.0 |      0.0 |
|   suite architecture_registry (s)                    |    496.7 |    421.8 |    328.6 |
|   PostgreSQL diag (s)                                |     40.1 |     92.3 |     57.1 |
|   porte AP diag (s)                                  |    236.1 |    340.9 |    289.3 |
| tests exécutés                                       |      204 |      204 |      204 |
| échecs + erreurs                                     |        0 |        0 |        0 |
| processus fils lancés par la suite (subprocess.run)  |       11 |       12 |       12 |
| copies du dépôt par la suite (copytree)              |      136 |      136 |      136 |
| CPU du processus principal de la suite (s)           |    200.5 |    183.6 |    173.0 |

Instantané avant chaque passe : A : CPU 33 %, RAM libre 373 Mo, 1 processus python; B : CPU 17 %, RAM libre 440 Mo, 1 processus python; C : CPU 17 %, RAM libre 340 Mo, 1 processus python

### Niveau 2 : suite par catégorie, durée murale cumulée (s)

|                                                      |        A |        B |        C |     moy. |    écart |  écart % |
|------------------------------------------------------|----------|----------|----------|----------|----------|----------|
| génération/vérification                              |     15.0 |      9.8 |     12.0 |     12.3 |      5.2 |     42.5 |
| injection                                            |    434.7 |    322.2 |    254.6 |    337.2 |    180.1 |     53.4 |
| mutation                                             |     13.0 |     11.2 |     15.4 |     13.2 |      4.2 |     31.9 |
| postgresql                                           |     28.1 |     67.7 |     38.6 |     44.8 |     39.6 |     88.3 |
| pur                                                  |      1.1 |      2.5 |      2.1 |      1.9 |      1.3 |     70.2 |
| sous-processus (résolution, gate)                    |      4.7 |      8.2 |      5.9 |      6.3 |      3.5 |     55.9 |

Nombre de tests par catégorie (passe A) : génération/vérification 52, injection 108, mutation 6, postgresql 1, pur 34, sous-processus (résolution, gate) 3

### Par module de test (s)

|                                                      |        A |        B |        C |     moy. |    écart |  écart % |
|------------------------------------------------------|----------|----------|----------|----------|----------|----------|
| test_ap_gaps                                         |     55.1 |    124.3 |     95.4 |     91.6 |     69.2 |     75.5 |
| test_ap_gate                                         |     17.8 |     19.5 |     21.3 |     19.5 |      3.6 |     18.2 |
| test_application                                     |    276.7 |    122.2 |    108.7 |    169.2 |    168.0 |     99.3 |
| test_contracts                                       |    112.1 |     76.6 |     55.7 |     81.5 |     56.4 |     69.2 |
| test_pg_locks                                        |     28.1 |     67.7 |     38.6 |     44.8 |     39.6 |     88.3 |
| test_registry                                        |      0.8 |      0.6 |      0.6 |      0.7 |      0.3 |     39.2 |
| test_runner_architecture                             |      6.0 |     10.7 |      8.2 |      8.3 |      4.6 |     55.9 |

Tests par module : test_ap_gaps 38, test_ap_gate 22, test_application 68, test_contracts 24, test_pg_locks 1, test_registry 37, test_runner_architecture 14

### Coût moyen d'un test d'injection (s) et de sa copie du dépôt (s)

|                                                      |        A |        B |        C |     moy. |    écart |  écart % |
|------------------------------------------------------|----------|----------|----------|----------|----------|----------|
| durée moyenne par test d'injection                   |      4.0 |      3.0 |      2.4 |      3.1 |      1.7 |     53.4 |
| dont copie du dépôt par test                         |      1.2 |      0.9 |      0.6 |      0.9 |      0.5 |     58.5 |

### Les 10 tests les plus lents (durée par passe, s)

- `test_pg_locks.TestPostgresLocks.test_all_experiments_confirm_the_architecture` : 28.1 / 67.7 / 38.6
- `test_application.TestReview.test_rv4_the_relay_claims_then_runs_handlers_then_marks_published` : 52.3 / 3.7 / 2.9
- `test_contracts.TestInjectedViolations.test_h_framework_import_is_forbidden` : 22.9 / 13.5 / 12.1
- `test_contracts.TestInjectedViolations.test_p3_port_outside_a_ports_file` : 14.9 / 7.0 / 2.5
- `test_application.TestReview.test_rv7_replay_is_not_universal` : 13.7 / 5.4 / 4.5
- `test_application.TestReview.test_rv6_a_worker_without_claim_is_refused` : 18.0 / 2.5 / 2.4
- `test_application.TestReview.test_rv6_an_external_effect_never_sits_in_a_transaction` : 15.4 / 2.3 / 2.1
- `test_application.TestTransactionScope.test_create_organization_is_new_and_only_it` : 6.8 / 8.0 / 4.0
- `test_contracts.TestInjectedViolations.test_p4_import_of_an_undeclared_dependency` : 11.7 / 4.1 / 2.4
- `test_ap_gaps.TestAP02Fidelity.test_a_drift_of_the_cross_module_calls_is_refused` : 3.1 / 12.0 / 2.6

### Niveau 3 : PostgreSQL par phase (s, sauf indication)

|                                                      |        A |        B |        C |     moy. |    écart |  écart % |
|------------------------------------------------------|----------|----------|----------|----------|----------|----------|
| import                                               |      1.2 |      3.5 |      2.0 |      2.2 |      2.3 |    100.7 |
| demarrage_a_froid (initdb + start)                   |     14.1 |     42.8 |     22.9 |     26.6 |     28.7 |    107.9 |
| connexion + select version                           |      0.1 |      0.2 |      0.2 |      0.2 |      0.2 |     81.7 |
| latence_requete_ms (moyenne de 200)                  |      0.5 |      1.0 |      1.0 |      0.8 |      0.4 |     51.9 |
| latence_connexion_ms (moyenne de 20)                 |     58.9 |     75.2 |     79.3 |     71.1 |     20.4 |     28.7 |
| remise_a_zero_schema (DROP/CREATE + fixtures)        |      2.0 |      2.7 |      2.8 |      2.5 |      0.8 |     32.1 |
| arret_du_serveur                                     |      0.6 |      0.7 |      0.6 |      0.7 |      0.1 |     17.7 |
| nettoyage_repertoire                                 |      0.4 |      0.9 |      0.8 |      0.7 |      0.5 |     66.0 |
| redemarrage_a_chaud (start seul)                     |      0.6 |      1.1 |      1.0 |      0.9 |      0.5 |     54.1 |
| total                                                |     40.1 |     92.3 |     57.1 |     63.2 |     52.2 |     82.7 |
| attentes_volontaires_des_experiences (sleep)         |      1.7 |      1.7 |      1.7 |      1.7 |      0.0 |      0.0 |

### Expériences PostgreSQL (s)

|                                                      |        A |        B |        C |     moy. |    écart |  écart % |
|------------------------------------------------------|----------|----------|----------|----------|----------|----------|
| e1_fk_insert_vs_lock_modes                           |      0.9 |      0.9 |      1.2 |      1.0 |      0.3 |     27.1 |
| e2_update_columns                                    |      0.4 |      0.5 |      0.4 |      0.4 |      0.1 |     22.6 |
| e3_locker_conflicts                                  |      1.6 |      1.9 |      1.7 |      1.7 |      0.2 |     13.0 |
| e4_deadlock                                          |      0.8 |      0.9 |      0.9 |      0.9 |      0.1 |     17.1 |
| e6_guarded_update                                    |      0.4 |      0.5 |      0.4 |      0.4 |      0.1 |     13.6 |
| e7_unique_insert_waits                               |      0.5 |      0.5 |      0.6 |      0.5 |      0.1 |     10.1 |
| e8_skip_locked                                       |      0.1 |      0.1 |      0.1 |      0.1 |      0.0 |     38.7 |
| e9_rls                                               |      0.2 |      0.4 |      0.3 |      0.3 |      0.2 |     62.0 |
| e5_advisory_snapshot                                 |      1.0 |      1.0 |      1.0 |      1.0 |      0.0 |      3.1 |

PostgreSQL : PostgreSQL 16.2 on x86_64-pc-mingw64 ; expériences exécutées : 10 ; toutes confirmées : True

### Porte AP par étape (s)

|                                                      |        A |        B |        C |     moy. |    écart |  écart % |
|------------------------------------------------------|----------|----------|----------|----------|----------|----------|
| resolution (subprocess list)                         |      1.4 |      1.7 |      1.9 |      1.7 |      0.5 |     29.7 |
| exécution des preuves (tests + injections)           |    141.1 |    187.6 |    176.5 |    168.4 |     46.5 |     27.6 |
| base de référence des mutations                      |      1.4 |      2.5 |      1.4 |      1.8 |      1.1 |     63.5 |
| 40 mutations (copie + application + tests)           |     92.2 |    149.1 |    109.5 |    116.9 |     56.9 |     48.6 |

### 40 mutations : ventilation (s)

|                                                      |        A |        B |        C |     moy. |    écart |  écart % |
|------------------------------------------------------|----------|----------|----------|----------|----------|----------|
| copie du dépôt                                       |     50.1 |     76.4 |     58.2 |     61.6 |     26.2 |     42.6 |
| processus de tests (unittest en sous-processus)      |     63.7 |    103.9 |     76.1 |     81.2 |     40.2 |     49.4 |

Mutations tuées : 40 sur 40 / 40 sur 40 / 40 sur 40

## Écarts entre passes

suite : min 328.6 s, max 496.7 s, écart 168.2 s (40.5 % de la moyenne)
