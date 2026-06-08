"""Tests for shared utility functions."""

import pytest

from bloomone.utils import (
    aa_to_dna,
    apply_mutation_and_generate_peptides,
    check_premature_stops,
    compute_peptide_identity,
    dna_to_mrna,
    find_proteome_matches,
    gc_content,
    generate_spanning_peptides,
    parse_hgvsp_short,
)


class TestParseHGVSp:
    def test_single_letter(self):
        assert parse_hgvsp_short("p.V600E") == (600, "V", "E")

    def test_three_letter(self):
        assert parse_hgvsp_short("p.Val600Glu") == (600, "V", "E")

    def test_another_mutation(self):
        assert parse_hgvsp_short("p.G13R") == (13, "G", "R")

    def test_invalid(self):
        assert parse_hgvsp_short("not_a_mutation") is None

    def test_none(self):
        assert parse_hgvsp_short(None) is None

    def test_empty(self):
        assert parse_hgvsp_short("") is None

    def test_frameshift(self):
        # Frameshifts should not parse (only missense)
        assert parse_hgvsp_short("p.V600fs") is None

    def test_stop_gain(self):
        assert parse_hgvsp_short("p.Val600Ter") == (600, "V", "*")


class TestPeptideGeneration:
    def test_basic_9mer(self):
        # Simple protein with mutation at position 5
        protein = "AAAAAVAAAA"  # 10 aa, V at position 6 (1-indexed)
        peptides = generate_spanning_peptides(protein, 5, kmer_lengths=[9])

        assert len(peptides) > 0
        for p in peptides:
            assert len(p["peptide"]) == 9
            assert p["peptide_length"] == 9

    def test_multi_kmer(self):
        protein = "AAAAAVAAAAA"  # 11 aa
        peptides = generate_spanning_peptides(
            protein, 5, kmer_lengths=[8, 9, 10, 11]
        )

        lengths = {p["peptide_length"] for p in peptides}
        assert 8 in lengths
        assert 9 in lengths

    def test_mutation_in_all_peptides(self):
        protein = "XXXXXMXXXXX"  # 11 aa, M at position 6
        peptides = generate_spanning_peptides(protein, 5, kmer_lengths=[9])

        for p in peptides:
            offset = p["mutation_offset_in_peptide"]
            assert p["peptide"][offset - 1] == "M"

    def test_skip_stop_codon(self):
        protein = "AAAA*AAAAA"
        peptides = generate_spanning_peptides(protein, 4, kmer_lengths=[9])
        for p in peptides:
            assert "*" not in p["peptide"]

    def test_apply_mutation(self):
        protein = "MADEKVRLF"  # 9 aa
        # Mutate K at position 5 (1-indexed) to E
        peptides = apply_mutation_and_generate_peptides(
            protein, 5, "K", "E", kmer_lengths=[9]
        )
        assert len(peptides) == 1
        assert peptides[0]["peptide"] == "MADEEVRLF"  # K→E at pos 5, full 9aa

    def test_ref_mismatch_returns_empty(self):
        protein = "MADEKVRLF"
        # Wrong ref AA (position 5 is K, not G)
        peptides = apply_mutation_and_generate_peptides(
            protein, 5, "G", "E", kmer_lengths=[9]
        )
        assert len(peptides) == 0

    def test_position_out_of_bounds(self):
        protein = "SHORT"
        peptides = apply_mutation_and_generate_peptides(
            protein, 100, "X", "Y", kmer_lengths=[9]
        )
        assert len(peptides) == 0


class TestCodonTranslation:
    def test_aa_to_dna(self):
        assert aa_to_dna("M") == "ATG"
        assert aa_to_dna("MK") == "ATGAAG"

    def test_dna_to_mrna(self):
        assert dna_to_mrna("ATGAAG") == "AUGAAG"

    def test_gc_content(self):
        assert gc_content("GGCC") == 100.0
        assert gc_content("AATT") == 0.0
        assert gc_content("ATGC") == 50.0

    def test_unknown_aa_raises(self):
        with pytest.raises(ValueError):
            aa_to_dna("Z")

    def test_premature_stops(self):
        # CDS with no premature stops: ATG ... TGA
        cds = "ATGGCCAAG" + "TGA"  # M A K *
        assert check_premature_stops(cds) == []

        # CDS with premature stop at codon 1 (after ATG)
        cds = "ATGTGAAAG" + "TGA"  # M * K *
        assert 1 in check_premature_stops(cds)


class TestSelfSimilarity:
    def test_exact_match(self):
        proteome = [("ProteinA", "XXXXXAAAAVXXXXX")]
        peptide = "AAAAV"
        matches = find_proteome_matches(peptide, proteome, 0.80)
        assert len(matches) > 0
        assert matches[0]["identity"] == 1.0

    def test_no_match(self):
        proteome = [("ProteinA", "WWWWWWWWWW")]
        peptide = "AAAAV"
        matches = find_proteome_matches(peptide, proteome, 0.80)
        assert len(matches) == 0

    def test_partial_match_above_threshold(self):
        proteome = [("ProteinA", "AAAAAVAAAA")]
        peptide = "AAAAV"  # 5mer, 4/5 match with "AAAAA" = 80%
        matches = find_proteome_matches(peptide, proteome, 0.80)
        # "AAAAV" should match "AAAAV" exactly (100%)
        assert len(matches) > 0

    def test_identity_computation(self):
        assert compute_peptide_identity("AAAA", "AAAA") == 1.0
        assert compute_peptide_identity("AAAA", "AABA") == 0.75
        assert compute_peptide_identity("AAAA", "BBBB") == 0.0

    def test_different_length_returns_zero(self):
        assert compute_peptide_identity("AAA", "AAAA") == 0.0
