import data from "./source-sites.json";

/** One site the corpus takes text from (corpus cleanup 4.4, About › Sources). */
export interface SourceSite {
  key: string;
  name: string;
  url: string;
  /** What the corpus takes from it. */
  taken: string;
  /** On what basis, one line per rights status its documents have. */
  basis: string[];
  /** The recorded basis for quoting in-copyright texts in excerpts, as the inventory
   *  states it, with how many documents rest on it. */
  excerpt_bases: { statement: string; url?: string | null; documents: number }[];
  /** `texts`: what each extract printed from this site supplies, where the document's
   *  main source is elsewhere or it has several. */
  documents: { document_id: string; title: string; collection: string; texts?: string[] }[];
}

/** Generated from the rights inventory by `datapipeline/scripts/source_sites.py`; never
 *  edited by hand. */
export const SOURCE_SITES: SourceSite[] = data.sites;
