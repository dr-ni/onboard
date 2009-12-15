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

#include <stdlib.h>
#include <stdio.h>
#include <algorithm>
#include <map>

#include "lm.h"

using namespace std;


// sorts an index array according to values from the cmp array, descending
template <class T, class TCMP>
void stable_argsort_desc(vector<T>& v, const vector<TCMP>& cmp)
{
    // Shellsort in place; stable, fast for already sorted arrays
    int i, j, gap;
    int n = v.size();
    T t;

    for (gap = n/2; gap > 0; gap >>= 1)
    {
        for (i = gap; i < n; i++)
        {
            for (j = i-gap; j >= 0; j -= gap)
            {
	            if (!(cmp[v[j]] < cmp[v[j+gap]]))
                    break;	

                // Swap p with q
                t = v[j+gap];
                v[j+gap] = v[j];
                v[j] = t;
            }
        }
    }
}

//------------------------------------------------------------------------
// Dictionary - contains the vocabulary of the language model
//------------------------------------------------------------------------

void Dictionary::clear()
{
    vector<wchar_t*>::iterator it;
    for (it=words.begin(); it < words.end(); it++)
        MemFree(*it);

    vector<wchar_t*>().swap(words);  // clear and really free the memory
    vector<WordId>().swap(sorted);
}

// Reserve an exact number of items to avoid unessarily
// overallocating memory when loading language models
void Dictionary::reserve_words(int count)
{
    clear();
    words.reserve(count);
    sorted.reserve(count);
}

// Look up the given word and return its id, binary search
WordId Dictionary::word_to_id(const wchar_t* word)
{
    int index = search_index(word);
    if (index >= 0 && index < (int)sorted.size())
    {
        WordId wid = sorted[index];
        if (wcscmp(words[wid], word) == 0)
            return wid;
    }
    return WIDNONE;
}

vector<WordId> Dictionary::words_to_ids(const wchar_t** word, int n)
{
    vector<WordId> wids;
    for(int i=0; i<n; i++)
        wids.push_back(word_to_id(word[i]));
    return wids;
}

// return the word for the given id, fast index lookup
wchar_t* Dictionary::id_to_word(WordId wid)
{
    if (0 <= wid && wid < (int)words.size())
        return words[wid];
    return NULL;
}

// Add a word to the dictionary
WordId Dictionary::add_word(const wchar_t* word)
{
    wchar_t* w = (wchar_t*)MemAlloc((wcslen(word) + 1) * sizeof(wchar_t));
    if (!w)
        return -1;
    wcscpy(w, word);

    WordId wid = (WordId)words.size();
    words.push_back(w);

    // bottle neck here, this is rather inefficient
    // everything else just appends, this inserts
    int index = search_index(w);
    sorted.insert(sorted.begin()+index, wid);

    //printf("%ls %d %d %d\n", w, wid, (int)words.size(), (int)words.capacity());

    return wid;
}

// Find all word ids of words starting with prefix
void Dictionary::prefix_search(const wchar_t* prefix, vector<WordId>& wids)
{
    // binary search for the first match
    // then linearly collect all subsequent matches
    int len = wcslen(prefix);
    int size = sorted.size();
    int index = search_index(prefix);
    for (int i=index; i<size; i++)
    {
        WordId wid = sorted[i];
        if (wcsncmp(words[wid], prefix, len) != 0)
            break;
        wids.push_back(wid);
    }
}

void Dictionary::prefix_search(const wchar_t* prefix, vector<wchar_t*>& words)
{
    // binary search for the first match
    // then linearly collect all subsequent matches
    int len = wcslen(prefix);
    int size = sorted.size();
    int index = search_index(prefix);
    for (int i=index; i<size; i++)
    {
        WordId wid = sorted[i];
        if (wcsncmp(words[wid], prefix, len) != 0)
            break;
        words.push_back(words[wid]);
    }
}

// Estimate a lower bound for the memory usage of the dictionary.
// This includes overallocations by std::vector, but excludes memory
// used for heap management and possible heap fragmentation.
uint64_t Dictionary::get_memory_size()
{
    uint64_t sum = 0;

    uint64_t d = sizeof(Dictionary);
    sum += d;

    uint64_t w = 0;
    for (unsigned i=0; i<words.size(); i++)
        w += sizeof(wchar_t) * (wcslen(words[i]) + 1);
    sum += w;

    uint64_t wc = sizeof(wchar_t*) * words.capacity();
    sum += wc;

    uint64_t sc = sizeof(WordId) * sorted.capacity();
    sum += sc;

    #ifndef NDEBUG
    printf("dictionary object: %12ld Byte\n", d);
    printf("strings:           %12ld Byte (%u)\n", w, (unsigned)words.size());
    printf("words.capacity:    %12ld Byte (%u)\n", wc, (unsigned)words.capacity());
    printf("sorted.capacity:   %12ld Byte (%u)\n", sc, (unsigned)sorted.capacity());
    printf("Dictionary total:  %12ld Byte\n", sum);
    #endif

    return sum;
}


//------------------------------------------------------------------------
// LanguageModel - base class of all language models
//------------------------------------------------------------------------

void LanguageModel::predict(std::vector<LanguageModel::Result>& results,
                            const std::vector<wchar_t*>& context,
                            int limit, bool filter_control_words, bool sort)
{
    int i;

    if (!context.size())
        return;

    // split context into history and prefix
    vector<wchar_t*> h;
    const wchar_t* prefix = split_context(context, h);
    vector<WordId> history = words_to_ids(h);

    // get candidate words
    vector<WordId> wids;
    get_candidates(prefix, wids, filter_control_words);

    // calculate probability vector
    vector<double> probabilities(wids.size());
    get_probs(history, wids, probabilities);

    // prepare results vector
    int result_size = wids.size();
    if (limit >= 0 && limit < result_size)
        result_size = limit;
    results.clear();
    results.reserve(result_size);

    if (sort)
    {
        // sort by descending probabilities
        vector<int32_t> argsort(wids.size());
        for (i=0; i<(int)wids.size(); i++)
            argsort[i] = i;
        stable_argsort_desc(argsort, probabilities);

        // merge word ids and probabilities into the return array
        for (i=0; i<result_size; i++)
        {
            int index = argsort[i];
            Result result = {id_to_word(wids[index]),
                             probabilities[index]};
            results.push_back(result);
        }
    }
    else
    {
        for (int i=0; i<result_size; i++)
        {
            Result result = {id_to_word(wids[i]),
                             probabilities[i]};
            results.push_back(result);
        }
    }
}

// Return the probability of a single n-gram.
// Not optimized for speed, inefficient to call this many times.
double LanguageModel::get_probability(const wchar_t* const* ngram, int n)
{
    if (!n)
        return 0.0;

    // split context into history and prefix
    const wchar_t* word = ngram[n-1];
    vector<WordId> history;
    for (int i=0; i<n-1; i++)
        history.push_back(word_to_id(ngram[i]));

    // get candidate word
    vector<WordId> wids(1, word_to_id(word));

    // calculate probability
    vector<double> vp(1);
    get_probs(history, wids, vp);

    return vp[0];
}

// split context into history and prefix
const wchar_t* LanguageModel::split_context(const vector<wchar_t*>& context,
                                                  vector<wchar_t*>& history)
{
    int n = context.size();
    wchar_t* prefix = context[n-1];
    for (int i=0; i<n-1; i++)
        history.push_back(context[i]);
    return prefix;
}


//------------------------------------------------------------------------
// LanguageModelNGram - base class of n-gram language models, may go away
//------------------------------------------------------------------------

#ifndef NDEBUG
void LanguageModelNGram::print_ngram(const std::vector<WordId>& wids)
{
    for (int i=0; i<(int)wids.size(); i++)
    {
        printf("%ls(%d)", id_to_word(wids[i]), wids[i]);
        if (i<(int)wids.size())
            printf(" ");
    }
    printf("\n");
}
#endif



//------------------------------------------------------------------------
// LinintModel - linearly interpolate language models
//------------------------------------------------------------------------

struct map_wstr_cmp
{
  bool operator() (const wchar_t* lhs, const wchar_t* rhs) const
  { return wcscmp(lhs, rhs) < 0;}
};
typedef std::map<const wchar_t*, double, map_wstr_cmp> ResultsMap;

struct cmp_results_desc
{
  bool operator() (const LanguageModel::Result& x, const LanguageModel::Result& y)
  { return (y.p < x.p);}
};


void LinintModel::predict(vector<LanguageModel::Result>& results,
                          const vector<wchar_t*>& context,
                          int limit, bool filter_control_words, bool sort)
{
    int i;

    // pad weights with default value in case there are too few entries
    vector<double> ws = weights;
    ws.resize(models.size(), 1.0);

    // precalculate divisor
    double wsum = 0;
    for (i=0; i<(int)models.size(); i++)
        wsum += ws[i];

    // interpolate prediction results of all models
    ResultsMap m;
    for (i=0; i<(int)models.size(); i++)
    {
        // always get all results, a limit could change the outcome
        vector<Result> rs;
        models[i]->predict(rs, context, -1, filter_control_words, false);
        double weight = ws[i] / wsum;

        vector<Result>::iterator it;
        for (it=rs.begin(); it != rs.end(); it++)
        {
            const wchar_t* word = it->word;
            double p = it->p;

            ResultsMap::iterator mit = m.insert(m.begin(),
                                       pair<const wchar_t*, double>(word, 0.0));
            mit->second += weight * p;
        }
    }

    // copy map to the results vector
    results.resize(0);
    results.reserve(m.size());
    ResultsMap::iterator mit;
    for (mit=m.begin(); mit != m.end(); mit++)
    {
        Result result = {mit->first, mit->second};
        results.push_back(result);
    }

    if (sort)
    {
        // sort by descending probabilities
        cmp_results_desc cmp_results;
        std::sort(results.begin(), results.end(), cmp_results);
    }

    // limit results, can't really do this earlier
    if (limit >= 0 && limit < (int)results.size())
        results.resize(limit);
}

double LinintModel::get_probability(const wchar_t* const* ngram, int n)
{
    int i;

    // pad weights with default value in case there are too few entries
    vector<double> ws = weights;
    ws.resize(models.size(), 1.0);

    // precalculate divisor
    double wsum = 0;
    for (i=0; i<(int)models.size(); i++)
        wsum += ws[i];

    // interpolate prediction results of all models
    double p = 0.0;
    for (i=0; i<(int)models.size(); i++)
    {
        double weight = ws[i] / wsum;
        p += weight * get_probability(ngram, n);
    }

    return p;
}


