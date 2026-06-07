import pandas as pd

maf = pd.read_csv("skcm_tcga_pan_can_atlas_2018/data_mutations.txt", sep="\t", comment="#")
missense = maf[maf["Variant_Classification"] == "Missense_Mutation"]
print(len(missense))
missense.to_csv("output/missense_mutations.csv", index=False)