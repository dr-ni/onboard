/*
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Author: marmuta <marmvta@gmail.com>
*/

#include "lm_dynamic.h"

using namespace std;

//------------------------------------------------------------------------
// DynamicModelBase
//------------------------------------------------------------------------

// Load from ARPA-like format, expects counts instead of log probabilities
// and no back-off values. N-grams don't have to be sorted alphabetically.
// State machine driven version, still the fastest.
LanguageModel::Error DynamicModelBase::load_arpac(const char* filename)
{
    int i;
    int new_order = 0;
    int current_level = 0;
    std::vector<int> counts;
    Error error = ERR_NONE;

    enum {BEGIN, COUNTS, NGRAMS_HEAD, NGRAMS, DONE}
    state = BEGIN;

    clear();

    FILE* f = fopen(filename, "r,ccs=UTF-8");
    if (!f)
    {
        #ifndef NDEBUG
        printf( "Error opening %s\n", filename);
        #endif
        return ERR_FILE;
    }

    while(1)
    {
        // read line
        wchar_t buf[4096];
        if (fgetws(buf, ALEN(buf), f) == NULL)
            break;

        // chop line into tokens
        wchar_t *tstate;
        wchar_t* tokens[32] = {wcstok(buf, L" \n", &tstate)};
        for (i=0; tokens[i] && i < ALEN(tokens)-1; i++)
            tokens[i+1] = wcstok(NULL, L" \n", &tstate);
        int ntoks = i;

        if (ntoks)  // any tokens there?
        {
            // check for n-grams first, this is by far the most frequent case
            if (state == NGRAMS)
            {
                if (tokens[0][0] == L'\\')  // end of section?
                {
                    if (get_num_ngrams(current_level-1) !=
                        counts[current_level-1])
                    {
                        error = ERR_COUNT; // count doesn't match number of unique ngrams
                        break;
                    }
                    state = NGRAMS_HEAD;
                }
                else
                {
                    if (ntoks < current_level+1)
                    {
                        error = ERR_NUMTOKENS; // too few tokens for cur. level
                        break;
                    }

                    int i = 0;
                    int count = wcstol(tokens[i++], NULL, 10);

                    uint32_t time = 0;
                    if (ntoks >= current_level+2)
                        time  = wcstol(tokens[i++], NULL, 10);


                    BaseNode* node = count_ngram(tokens+i,
                                                 current_level, count);
                    if (!node)
                    {
                        error = ERR_MEMORY; // out of memory
                        break;
                    }

                    set_node_time(node, time);

                    continue;
                }
            }
            else
            if (state == BEGIN)
            {
                if (wcsncmp(tokens[0], L"\\data\\", 6) == 0)
                {
                    state = COUNTS;
                }
            }
            else
            if (state == COUNTS)
            {
                if (wcsncmp(tokens[0], L"ngram", 5) == 0 && ntoks >= 2)
                {
                    int level;
                    int count;
                    if (swscanf(tokens[1], L"%d=%d", &level, &count) == 2)
                    {
                        new_order = std::max(new_order, level);
                        counts.resize(new_order);
                        counts[level-1] = count;
                    }
                }
                else
                {
                    // clear language model and set it up for the new order
                    set_order(new_order);
                    if (new_order)
                    {
                        dictionary.reserve_words(counts[0]);
                        reserve_unigrams(counts[0]);
                    }
                    state = NGRAMS_HEAD;
                }
            }

            if (state == NGRAMS_HEAD)
            {
                if (swscanf(tokens[0], L"\\%d-grams", &current_level) == 1)
                {
                    if (current_level < 1 || current_level > new_order)
                    {
                        error = ERR_ORDER;
                        break;
                    }
                    state = NGRAMS;
                }
                else
                if (wcsncmp(tokens[0], L"\\end\\", 5) == 0)
                {
                    state = DONE;
                    break;
                }
            }
        }
    }

    // didn't make it until the end?
    if (state != DONE)
    {
        clear();
        if (!error)
            error = ERR_UNEXPECTED_EOF;  // unexpected end of file
    }

    return error;
}


// Save to ARPA-like format, stores counts instead of log probabilities
// and no back-off values.
LanguageModel::Error DynamicModelBase::save_arpac(const char* filename)
{
    int i;

    FILE* f = fopen(filename, "w,ccs=UTF-8");
    if (!f)
    {
        #ifndef NDEBUG
        printf( "Error opening %s\n", filename);
        #endif
        return ERR_FILE;
    }

    fwprintf(f, L"\n");
    fwprintf(f, L"\\data\\\n");

    for (i=0; i<order; i++)
        fwprintf(f, L"ngram %d=%d\n", i+1, get_num_ngrams(i));

    write_arpa_ngrams(f);

    fwprintf(f, L"\n");
    fwprintf(f, L"\\end\\\n");

    fclose(f);

    return ERR_NONE;
}

LanguageModel::Error DynamicModelBase::write_arpa_ngrams(FILE* f)
{
    int i;

    for (i=0; i<order; i++)
    {
        fwprintf(f, L"\n");
        fwprintf(f, L"\\%d-grams:\n", i+1);

        std::vector<WordId> wids;
        DynamicModelBase::ngrams_iter* it;
        for (it = ngrams_begin(); ; (*it)++)
        {
            BaseNode* node = *(*it);
            if (!node)
                break;

            if (it->get_level() == i+1)
            {
                it->get_ngram(wids);
                LanguageModel::Error error = write_arpa_ngram(f, node, wids);
                if (error)
                    return error;
            }
        }
    }

    return ERR_NONE;
}

