"""La porte de fermeture (`verify_ap.py`) tient sa promesse : un invariant sans preuve, une preuve orpheline, une référence qui ne se résout pas, une mutation invalide
ou qui survit sont tous des ÉCHECS. Un développeur qui ajoute `AP-16` sans sa preuve fait tomber la CI.

Lancement : python -m unittest test_ap_gate (dans architecture_registry/)
"""
import copy
import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ap_catalogue  # noqa: E402
import ap_mutations  # noqa: E402
import ap_proofs  # noqa: E402
import verify_ap as V  # noqa: E402

RUNNER = 'application_runner/runner.py'


def check(catalogue=None, proofs=None, mutations=None, resolve=False):
    return V.check(catalogue=catalogue, proofs=proofs, mutations=mutations, resolve=resolve)


class TestTheRealRegistry(unittest.TestCase):
    def test_the_fifteen_invariants_are_referenced_resolved_and_complete(self):
        errors, detail = check(resolve=True)
        self.assertEqual(errors, [])
        self.assertEqual(len(detail), 15)
        self.assertEqual(sum(1 for d in detail.values() if d['errors']), 0)                       # PROVEN_AP = 15
        self.assertEqual(sum(1 for d in detail.values() if not d['tests']), 0)                    # UNTESTED_AP = 0
        for ap, d in detail.items():
            self.assertTrue(d['tests'], ap)                                                       # au moins un test
            self.assertTrue(d['inject'] or d['code'], ap)                                         # au moins une mutation
            self.assertTrue(ap_proofs.PROOFS[ap]['static'], ap)                                   # une vérification statique

    def test_the_catalogue_is_the_contract_not_a_copy(self):
        """Les invariants du catalogue sont ceux du document gelé : le catalogue est leur SOURCE, le document en dérive."""
        with io.open(os.path.join(os.path.dirname(V.HERE), 'APPLICATION_CONTRACT_V1.md'), encoding='utf-8') as f:
            text = f.read()
        rows = re.findall(r'^\| (AP-\d+) \| (.*?) \| (.*?) \|$', text, re.M)
        self.assertEqual([r[0] for r in rows], [a for a, _, _ in ap_catalogue.INVARIANTS])
        self.assertEqual([r[1] for r in rows], [t for _, t, _ in ap_catalogue.INVARIANTS])

    def test_every_static_property_named_by_a_proof_exists_in_the_verifier(self):
        for ap, proof in ap_proofs.PROOFS.items():
            for code in proof['static']:
                self.assertIn(code, V.static_codes(), (ap, code))

    def test_the_proofs_document_is_in_sync_with_the_generator(self):
        errors, detail = check(resolve=True)
        with io.open(V.DOC, encoding='utf-8', newline='') as f:
            self.assertEqual(f.read(), V.render_doc(detail))

    def test_every_code_mutation_pattern_exists_exactly_as_declared_in_the_real_code(self):
        """Une mutation dont le motif est introuvable n'est pas un succès : c'est ce qui a déjà laissé passer une suite verte."""
        for m in ap_mutations.MUTATIONS:
            for rel, old, new, count in m.edits:
                with io.open(os.path.join(V.REAL_APP, rel.replace('/', os.sep)), encoding='utf-8') as f:
                    self.assertEqual(f.read().count(old), count, '%s : %s' % (m.id, rel))

    def test_every_mutation_is_referenced_by_its_own_invariant_and_none_is_orphan(self):
        referenced = {m[len('code:'):] for p in ap_proofs.PROOFS.values() for m in p['mutations'] if m.startswith('code:')}
        self.assertEqual(referenced, {m.id for m in ap_mutations.MUTATIONS})
        for m in ap_mutations.MUTATIONS:
            self.assertIn('code:' + m.id, ap_proofs.PROOFS[m.ap]['mutations'])


class TestAnInvariantWithoutItsProofFailsTheGate(unittest.TestCase):
    def test_a_new_invariant_ap_16_without_proof_fails(self):
        catalogue = list(ap_catalogue.INVARIANTS) + [('AP-16', 'Un invariant ajouté sans preuve', 'A99')]
        errors, detail = check(catalogue=catalogue)
        self.assertTrue(any(e.startswith('AP-16 : aucune preuve') for e in errors))
        self.assertTrue(detail['AP-16']['errors'])
        self.assertEqual(sum(1 for d in detail.values() if not d['errors']), 15)                  # les quinze autres restent prouvés : la porte désigne AP-16

    def test_a_proof_without_an_invariant_is_orphan(self):
        proofs = dict(ap_proofs.PROOFS, **{'AP-99': dict(static=('A1',), tests=('reg:x',), mutations=('code:M',))})
        errors, _ = check(proofs=proofs)
        self.assertTrue(any(e.startswith('AP-99 : preuve ORPHELINE') for e in errors))

    def test_an_invariant_without_tests_fails(self):
        proofs = copy.deepcopy(ap_proofs.PROOFS)
        proofs['AP-07']['tests'] = ()
        errors, detail = check(proofs=proofs)
        self.assertTrue(any(e.startswith('AP-07 : aucun test') for e in errors))
        self.assertTrue(detail['AP-07']['errors'])

    def test_an_invariant_without_a_mutation_fails(self):
        proofs = copy.deepcopy(ap_proofs.PROOFS)
        proofs['AP-12']['mutations'] = ()
        errors, _ = check(proofs=proofs)
        self.assertTrue(any(e.startswith('AP-12 : aucune mutation') for e in errors))

    def test_an_invariant_without_a_static_check_fails(self):
        proofs = copy.deepcopy(ap_proofs.PROOFS)
        proofs['AP-03']['static'] = ()
        errors, _ = check(proofs=proofs)
        self.assertTrue(any(e.startswith('AP-03 : aucune vérification statique') for e in errors))

    def test_an_unknown_static_property_fails(self):
        proofs = copy.deepcopy(ap_proofs.PROOFS)
        proofs['AP-03']['static'] = ('A99',)
        errors, _ = check(proofs=proofs)
        self.assertTrue(any('propriété statique inconnue `A99`' in e for e in errors))

    def test_a_mutation_form_that_is_neither_inject_nor_code_fails(self):
        proofs = copy.deepcopy(ap_proofs.PROOFS)
        proofs['AP-03']['mutations'] = tuple(proofs['AP-03']['mutations']) + ('un test quelque part',)
        errors, _ = check(proofs=proofs)
        self.assertTrue(any('mutation de forme inconnue' in e for e in errors))

    def test_a_code_mutation_that_does_not_exist_fails(self):
        proofs = copy.deepcopy(ap_proofs.PROOFS)
        proofs['AP-03']['mutations'] = tuple(proofs['AP-03']['mutations']) + ('code:M-INEXISTANTE',)
        errors, _ = check(proofs=proofs)
        self.assertTrue(any('mutation de code `M-INEXISTANTE` inexistante' in e for e in errors))

    def test_an_orphan_mutation_fails(self):
        extra = list(ap_mutations.MUTATIONS) + [ap_mutations.Mutation('M-ORPHELINE', 'AP-03', (), ())]
        errors, _ = check(mutations=extra)
        self.assertTrue(any(e.startswith('M-ORPHELINE : mutation ORPHELINE') for e in errors))

    def test_a_reference_that_does_not_resolve_fails(self):
        proofs = copy.deepcopy(ap_proofs.PROOFS)
        proofs['AP-05']['tests'] = tuple(proofs['AP-05']['tests']) + ('run:application_runner.tests.test_nowhere.TestGhost',)
        proofs['AP-05']['mutations'] = tuple(proofs['AP-05']['mutations']) + ('inject:reg:test_application.TestInjection.test_zz_*',)
        errors, _ = check(proofs=proofs, resolve=True)
        self.assertTrue(any('référence introuvable `run:application_runner.tests.test_nowhere.TestGhost`' in e for e in errors))
        self.assertTrue(any('test_zz_*' in e and e.startswith('AP-05') for e in errors))


class TestTheMutationEngine(unittest.TestCase):
    """Le moteur de mutation distingue TUÉE, SURVIVANTE et INVALIDE : un motif introuvable ne passe jamais pour un succès."""
    KILL = ('application_runner.tests.test_lock_order.TestLadderComesFromTheRegistry',)

    def test_a_pattern_that_is_not_found_is_invalid_never_a_pass(self):
        status, note = V.run_mutation(ap_mutations.Mutation('M-X', 'AP-03', ((RUNNER, 'ce texte n existe pas', 'x', 1),), self.KILL))
        self.assertEqual(status, 'invalid')
        self.assertIn('motif introuvable', note)

    def test_a_wrong_occurrence_count_is_invalid(self):
        status, _ = V.run_mutation(ap_mutations.Mutation('M-X', 'AP-03', ((RUNNER, 'import copy', 'import copy', 5),), self.KILL))
        self.assertEqual(status, 'invalid')

    def test_a_harmless_edit_survives(self):
        status, _ = V.run_mutation(ap_mutations.Mutation('M-X', 'AP-03', ((RUNNER, 'import copy', 'import copy  # inoffensif', 1),), self.KILL))
        self.assertEqual(status, 'survived')

    def test_a_guard_removal_is_killed(self):
        status, note = V.run_mutation(ap_mutations.Mutation('M-X', 'AP-03', (('application_runner/doubles/locks.py', '        if rank <= uow.last_rank:', '        if False:', 1),), self.KILL))
        self.assertEqual(status, 'killed')

    def test_a_mutation_that_breaks_loading_is_invalid_not_killed(self):
        status, _ = V.run_mutation(ap_mutations.Mutation('M-X', 'AP-03', ((RUNNER, 'import copy', 'import copy )(', 1),), self.KILL))
        self.assertEqual(status, 'invalid')

    def test_the_baseline_of_the_designated_tests_is_green(self):
        ok, tail = V.baseline_of_kills(ap_mutations.MUTATIONS)
        self.assertTrue(ok, tail)


if __name__ == '__main__':
    unittest.main()
