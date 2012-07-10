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

#include <stdio.h>
#include <assert.h>
#include <cstring>
#include <set>
#include <iostream>
#include <locale>

//------------------------------------------------------------------------
// NGramTrie - root node of the ngram trie
//------------------------------------------------------------------------

// Look up node or create it if it doesn't exist
template <class TNODE, class TBEFORELASTNODE, class TLASTNODE>
BaseNode* NGramTrie<TNODE, TBEFORELASTNODE, TLASTNODE>::
    add_node(const WordId* wids, int n)
{
    BaseNode* node = this;
    BaseNode* parent = NULL;
    TNODE* grand_parent = NULL;
    int parent_index = 0;
    int grand_parent_index = 0;

    for (int i=0; i<n; i++)
    {
        WordId wid = wids[i];
        grand_parent = static_cast<TNODE*>(parent);
        parent = node;
        grand_parent_index = parent_index;
        node = get_child(parent, i, wid, parent_index);
        if (!node)
        {
            if (i == order-1)
            {
                TBEFORELASTNODE* p = static_cast<TBEFORELASTNODE*>(parent);

                // check the available space for LastNodes
                int size = p->children.size();
                int old_capacity = p->children.capacity();
                if (size >= old_capacity)  // no space for another TLASTNODE?
                {
                    // grow the memory block of the parent node
                    int new_capacity = p->children.capacity(size + 1);
                    int old_bytes = sizeof(TBEFORELASTNODE) +
                               old_capacity*sizeof(TLASTNODE);
                    int new_bytes = sizeof(TBEFORELASTNODE) +
                               new_capacity*sizeof(TLASTNODE);
                    TBEFORELASTNODE* pnew = (TBEFORELASTNODE*) MemAlloc(new_bytes);
                    if (!pnew)
                        return NULL;

                    // copy the data over, no need for constructor calls
                    memcpy(pnew, p, old_bytes);

                    // replace grand_parent pointer
                    ASSERT(p == grand_parent->children[grand_parent_index]);
                    grand_parent->children[grand_parent_index] = pnew;
                    MemFree(p);
                    p = pnew;
                }

                // add the new child node
                node = p->add_child(wid);
            }
            else
            if (i == order-2)
            {
                int bytes = sizeof(TBEFORELASTNODE) +
                        inplace_vector<TLASTNODE>::capacity(0)*sizeof(TLASTNODE);
                TBEFORELASTNODE* nd = (TBEFORELASTNODE*)MemAlloc(bytes);
                //node = new TBEFORELASTNODE(wid);
                if (!nd)
                    return NULL;
                node = new(nd) TBEFORELASTNODE(wid);
                static_cast<TNODE*>(parent)->add_child(node);
            }
            else
            {
                TNODE* nd = (TNODE*)MemAlloc(sizeof(TNODE));
                if (!nd)
                    return NULL;
                node = new(nd) TNODE(wid);
                static_cast<TNODE*>(parent)->add_child(node);
            }

            num_ngrams[i]++; // keep track of the counts to avoid
                             // traversing the tree for these numbers
            break;
        }
    }
    return node;
}

template <class TNODE, class TBEFORELASTNODE, class TLASTNODE>
void NGramTrie<TNODE, TBEFORELASTNODE, TLASTNODE>::
    get_probs_witten_bell_i(const std::vector<WordId>& history,
                             const std::vector<WordId>& words,
                             std::vector<double>& vp,
                             int num_word_types)
{
    int i,j;
    int n = history.size() + 1;
    int size = words.size();   // number of candidate words
    std::vector<int32_t> vc(size);  // vector of counts, reused for order 1..n

    // order 0
    vp.resize(size);
    fill(vp.begin(), vp.end(), 1.0/num_word_types); // uniform distribution

    // order 1..n
    for(j=0; j<n; j++)
    {
        std::vector<WordId> h(history.begin()+(n-j-1), history.end()); // tmp history
        BaseNode* hnode = get_node(h);
        if (hnode)
        {
            int N1prx = get_N1prx(hnode, j);   // number of word types following the history
            if (!N1prx)  // break early, don't reset probabilities to 0
                break;   // for unknown histories

            // total number of occurences of the history
            int cs = sum_child_counts(hnode, j);
            if (cs)
            {
                // get ngram counts
                fill(vc.begin(), vc.end(), 0);
                int num_children = get_num_children(hnode, j);
                for(i=0; i<num_children; i++)
                {
                    BaseNode* child = get_child_at(hnode, j, i);
                    int index = binsearch(words, child->word_id); // word_indices have to be sorted by index
                    if (index >= 0)
                        vc[index] = child->get_count();
                }

                double l1 = N1prx / (N1prx + float(cs)); // normalization factor
                                                         // 1 - lambda
                for(i=0; i<size; i++)
                {
                    double pmle = vc[i] / float(cs);
                    vp[i] = (1.0 - l1) * pmle + l1 * vp[i];
                }
            }
        }
    }
}

// absolute discounting
template <class TNODE, class TBEFORELASTNODE, class TLASTNODE>
void NGramTrie<TNODE, TBEFORELASTNODE, TLASTNODE>::
     get_probs_abs_disc_i(const std::vector<WordId>& history,
                          const std::vector<WordId>& words,
                          std::vector<double>& vp,
                          int num_word_types,
                          const std::vector<double>& Ds)
{
    int i,j;
    int n = history.size() + 1;
    int size = words.size();   // number of candidate words
    std::vector<int32_t> vc(size);  // vector of counts, reused for order 1..n

    // order 0
    vp.resize(size);
    fill(vp.begin(), vp.end(), 1.0/num_word_types); // uniform distribution

    // order 1..n
    for(j=0; j<n; j++)
    {
        std::vector<WordId> h(history.begin()+(n-j-1), history.end()); // tmp history
        BaseNode* hnode = get_node(h);
        if (hnode)
        {
            int N1prx = get_N1prx(hnode, j);   // number of word types following the history
            if (!N1prx)  // break early, don't reset probabilities to 0
                break;   // for unknown histories

            // total number of occurences of the history
            int cs = sum_child_counts(hnode, j);
            if (cs)
            {
                // get ngram counts
                fill(vc.begin(), vc.end(), 0);
                int num_children = get_num_children(hnode, j);
                for(i=0; i<num_children; i++)
                {
                    BaseNode* child = get_child_at(hnode, j, i);
                    int index = binsearch(words, child->word_id); // word_indices have to be sorted by index
                    if (index >= 0)
                        vc[index] = child->get_count();
                }

                double D = Ds[j];
                double l1 = D / float(cs) * N1prx; // normalization factor
                                                   // 1 - lambda
                for(i=0; i<size; i++)
                {
                    double a = vc[i] - D;
                    if (a < 0)
                        a = 0;
                    vp[i] = a / float(cs) + l1 * vp[i];
                }
            }
        }
    }
}

//------------------------------------------------------------------------
// DynamicModel - dynamically updatable language model
//------------------------------------------------------------------------
template <class TNGRAMS>
void _DynamicModel<TNGRAMS>::set_order(int n)
{
    n1s = std::vector<int>(n, 0);
    n2s = std::vector<int>(n, 0);
    Ds  = std::vector<double>(n, 0);

    ngrams.set_order(n);
    NGramModel::set_order(n);  // calls clear()
}

template <class TNGRAMS>
void _DynamicModel<TNGRAMS>::clear()
{
    NGramModel::clear();  // clears dictionary

    ngrams.clear();

    // Add entries for control words.
    // Add them with a count of 1 as 0 throws off the normalization
    // of witten-bell smoothing.
    const wchar_t* words[] = {L"<unk>", L"<s>", L"</s>", L"<num>"};
    for (int i=0; i<ALEN(words); i++)
    {
        count_ngram(words+i, 1, 1);
        assert(dictionary.word_to_id(words[i]) == i);
    }
}

// Add increment to the count of the given ngram.
// Unknown words will be added to the dictionary and
// unknown ngrams will cause new trie nodes to be created as needed.
template <class TNGRAMS>
BaseNode* _DynamicModel<TNGRAMS>::count_ngram(const wchar_t* const* ngram, int n,
                                      int increment, bool allow_new_words)
{
    int i;
    std::vector<WordId> wids(n);

    // get/add word
    for (i = 0; i < n; i++)
    {
        const wchar_t* word = ngram[i];

        WordId wid = dictionary.word_to_id(word);
        if (wid == WIDNONE)
        {
            if (allow_new_words)
            {
                wid = dictionary.add_word(word);
                if (wid == WIDNONE)
                    return NULL;
            }
            else
            {
                wid = UNKNOWN_WORD_ID;
            }
        }
        wids[i] = wid;
    }

    return count_ngram(&wids[0], n, increment);
}

// Add increment to the count of the given ngram.
// Unknown words will be added to the dictionary first and
// unknown ngrams will cause new trie nodes to be created as needed.
template <class TNGRAMS>
BaseNode* _DynamicModel<TNGRAMS>::count_ngram(const WordId* wids, int n,
                                        int increment)
{
    int i;

    // get/add node for ngram
    BaseNode* node = ngrams.add_node(wids, n);
    if (!node)
        return NULL;

    // remove old state
    if (node->count == 1)
        n1s[n-1]--;
    if (node->count == 2)
        n2s[n-1]--;

    int count = increment_node_count(node, wids, n, increment);

    // add new state
    if (node->count == 1)
        n1s[n-1]++;
    if (node->count == 2)
        n2s[n-1]++;

    // estimate discounting parameters for absolute discounting, kneser-ney
    for (i = 0; i < order; i++)
    {
        double D;
        int n1 = n1s[i];
        int n2 = n2s[i];
        if (n1 == 0 || n2 == 0)
            D = 0.1;          // training corpus too small, fake a value
        else
            // deleted estimation, Ney, Essen, and Kneser 1994
            D = n1 / (n1 + 2.0*n2);
        ASSERT(0 <= D and D <= 1.0);
        //D = 0.1;
        Ds[i] = D;
    }

    return count >= 0 ? node : NULL;
}

// Return the number of occurences of the given ngram
template <class TNGRAMS>
int _DynamicModel<TNGRAMS>::get_ngram_count(const wchar_t* const* ngram, int n)
{
    BaseNode* node = get_ngram_node(ngram, n);
    return (node ? node->get_count() : 0);
}

// Calculate a vector of probabilities for the ngrams formed
// from history + word[i], for all i.
// input:  constant history and a vector of candidate words
// output: vector of probabilities, one value per candidate word
template <class TNGRAMS>
void _DynamicModel<TNGRAMS>::get_probs(const std::vector<WordId>& history,
                            const std::vector<WordId>& words,
                            std::vector<double>& probabilities)
{
    // pad/cut history so it's always of length order-1
    int n = std::min((int)history.size(), order-1);
    std::vector<WordId> h(order-1, UNKNOWN_WORD_ID);
    copy_backward(history.end()-n, history.end(), h.end());

    #ifndef NDEBUG
    for (int i=0; i<order; i++)
        printf("%d: n1=%8d n2=%8d D=%f\n", i, n1s[i], n2s[i], Ds[i]);
    #endif

    switch(smoothing)
    {
        case WITTEN_BELL_I:
            ngrams.get_probs_witten_bell_i(h, words, probabilities,
                                              get_num_word_types());
            break;

        case ABS_DISC_I:
            ngrams.get_probs_abs_disc_i(h, words, probabilities,
                                           get_num_word_types(), Ds);
            break;

         default:
            break;
    }
}

template <class TNGRAMS>
LanguageModel::Error _DynamicModel<TNGRAMS>::
write_arpa_ngram(FILE* f, const BaseNode* node, const std::vector<WordId>& wids)
{
    fwprintf(f, L"%d", node->get_count());

    std::vector<WordId>::const_iterator it;
    for(it = wids.begin(); it != wids.end(); it++)
        fwprintf(f, L" %ls", id_to_word(*it));

    fwprintf(f, L"\n");

    return ERR_NONE;
}

#if 0
// Load from ARPA-like format, expects counts instead of log probabilities
// and no back-off values. N-grams don't have to be sorted alphabetically.
// Non-state machine version, but turned out to be slower than the original.
template <class TNGRAMS>
LanguageModel::Error _DynamicModel<TNGRAMS>::
load_arpac(const char* filename)
{
    LanguageModel::Error error = ERR_NONE;
    wchar_t* text = NULL;

    clear();

    try
    {
        Error err = read_utf8(filename, text);
        if (err)
            throw err;

        // chop text into lines
        std::vector<wchar_t*> lines;
        wchar_t* lstate;
        wchar_t* line = wcstok(text, L"\r\n", &lstate);
        while(line)
        {
            wchar_t* p;
            for(p=line; iswspace(*p); p++);  // skip leading spaces
            if (*p != L'\0')                 // skip empty lines
                lines.push_back(p);
            line = wcstok(NULL, L"\r\n", &lstate);
        }

        std::vector<wchar_t*>::iterator it = lines.begin();

        // data section, header
        while(it != lines.end())
            if (wcsncmp(*it++, L"\\data\\", 6) == 0)
                break;
        if (it == lines.end())
            throw ERR_UNEXPECTED_EOF;

        // data section, content
        int new_order = 0;
        std::vector<int> counts;   // ngram counts
        while(it != lines.end())
        {
            wchar_t* line = *it;
            const wchar_t str[] = L"ngram";
            if (wcsncmp(line, str, wcslen(str)) == 0)
            {
                int level;
                int count;
                if (swscanf(line+wcslen(str), L"%d=%d", &level, &count) == 2)
                {
                    new_order = std::max(new_order, level);
                    counts.resize(new_order);
                    counts[level-1] = count;
                }
            }
            else
                break;

            it++;
        }

        // clear language model and set it up for the new order
        if (!new_order)
            throw ERR_ORDER;   // no ngram descriptions found
        set_order(new_order);
        dictionary.reserve_words(counts[0]);
        ngrams.reserve_unigrams(counts[0]);

        // ngram sections
        int current_level = -1;
        bool done = false;
        while(true)
        {
            // ngrams header
            while(it != lines.end())
            {
                wchar_t* line = *it++;
                if (swscanf(line, L"\\%d-grams", &current_level) == 1)
                {
                    if (current_level < 1 || current_level > new_order)
                        throw ERR_ORDER;  // ngrams for unknown order
                    break;
                }

                if (wcsncmp(line, L"\\end\\", 5) == 0)
                {
                    done = true;
                    break;
                }
            }

            if (done)
                break;
            if (it == lines.end())
                throw ERR_UNEXPECTED_EOF;

            // ngrams data
            while(it != lines.end())
            {
                wchar_t* line = *it;
                if (line[0] == L'\\')  // end of section?
                {
                    if (ngrams.get_num_ngrams(current_level-1) !=
                        counts[current_level-1])
                        throw ERR_COUNT; // count doesn't match number of unique ngrams
                    break;
                }

                // chop line into tokens
                wchar_t *tstate;
                wchar_t* tokens[32] = {wcstok(line, L" \n", &tstate)};
                int i;
                for (i=0; tokens[i] && i < ALEN(tokens)-1; i++)
                    tokens[i+1] = wcstok(NULL, L" \n", &tstate);
                int ntoks = i;

                if (ntoks < current_level+1)
                    throw ERR_NUMTOKENS; // too few tokens for current level

                i = 0;
                int count = wcstol(tokens[i++], NULL, 10);

                uint32_t time = 0;
                if (ntoks >= current_level+2)
                    time  = wcstol(tokens[i++], NULL, 10);

                BaseNode* node = count_ngram(tokens+i, current_level, count);
                if (!node)
                    throw ERR_MEMORY; // out of memory

                set_node_time(node, time);  // only implemented by UserModels

                it++;
            }
        }
    }
    catch (LanguageModel::Error e)
    {
        error = e;
        clear();
    }

    if (text)
        delete [] text;

    return error;
}

#else
// Load from ARPA-like format, expects counts instead of log probabilities
// and no back-off values. N-grams don't have to be sorted alphabetically.
// State machine driven version, still the fastest.
template <class TNGRAMS>
LanguageModel::Error _DynamicModel<TNGRAMS>::
load_arpac(const char* filename)
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
                    if (ngrams.get_num_ngrams(current_level-1) !=
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
                        error = ERR_NUMTOKENS; // too few tokens for current
                        break;
                    }

                    int i = 0;
                    int count = wcstol(tokens[i++], NULL, 10);

                    uint32_t time = 0;
                    if (ntoks >= current_level+2)
                        time  = wcstol(tokens[i++], NULL, 10);

                    BaseNode* node = count_ngram(tokens+i, current_level, count);
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
                        ngrams.reserve_unigrams(counts[0]);
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

    // not made it until the end?
    if (state != DONE)
    {
        clear();
        if (!error)
            error = ERR_UNEXPECTED_EOF;  // unexpected end of file
    }

    return error;
}
#endif

// Save to ARPA-like format, stores counts instead of log probabilities
// and no back-off values.
template <class TNGRAMS>
LanguageModel::Error _DynamicModel<TNGRAMS>::
save_arpac(const char* filename)
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
        fwprintf(f, L"ngram %d=%d\n", i+1, ngrams.get_num_ngrams(i));

    for (i=0; i<order; i++)
    {
        fwprintf(f, L"\n");
        fwprintf(f, L"\\%d-grams:\n", i+1);

        std::vector<WordId> wids;
        for (typename TNGRAMS::iterator it = ngrams.begin(); *it; it++)
        {
            if (it.get_level() == i+1)
            {
                it.get_ngram(wids);
                write_arpa_ngram(f, *it, wids);
            }
        }
    }

    fwprintf(f, L"\n");
    fwprintf(f, L"\\end\\\n");

    fclose(f);

    return ERR_NONE;
}

// load from format with depth first ngram traversal
// not much faster than load_arpa and more unusual file format -> disabled
template <class TNGRAMS>
LanguageModel::Error _DynamicModel<TNGRAMS>::
load_depth_first(const char* filename)
{
    int i;
    int new_order = 0;
    std::vector<int> counts;
    std::vector<WordId> wids;
    Error error = ERR_NONE;

    enum {BEGIN, COUNTS, NGRAMS_HEAD, NGRAMS, END, DONE}
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
        wchar_t buf[2048];
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
            // check for n-grams first
            if (state == NGRAMS)
            {
                if (tokens[0][0] == L'\\')
                {
                    for (i=0; i<new_order;i++)
                        if (ngrams.get_num_ngrams(i) != counts[i])
                    {
                        error = ERR_COUNT; // count doesn't match number of
                                           // unique ngrams
                        break;
                    }
                    state = END;
                }
                else
                {
                    if (ntoks < 3)
                    {
                        error = ERR_NUMTOKENS; // too few tokens for current ngram level
                        break;
                    }
                    int level = wcstol(tokens[0], NULL, 10);
                    int count = wcstol(tokens[1], NULL, 10);
                    const wchar_t* word = tokens[2];

                    WordId wid = dictionary.word_to_id(word);
                    if (wid == WIDNONE)
                    {
                        wid = dictionary.add_word(word);
                        if (wid == WIDNONE)
                        {
                            error = ERR_MEMORY;
                            break;
                        }
                    }
                    wids[level-1] = wid;

                    if (!count_ngram(&wids[0], level, count))
                    {
                        error = ERR_MEMORY; // out of memory
                        break;
                    }

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
                        ngrams.reserve_unigrams(counts[0]);
                        wids = std::vector<WordId>(new_order, 0);
                    }
                    state = NGRAMS_HEAD;
                }
            }

            if (state == NGRAMS_HEAD)
            {
                if (wcsncmp(tokens[0], L"\\n-grams:", 9) == 0)
                {
                    state = NGRAMS;
                }
            }

            if (state == END)
            {
                if (wcsncmp(tokens[0], L"\\end\\", 5) == 0)
                {
                    state = DONE;
                    break;
                }
            }
        }
    }

    // not made it until the end?
    if (state != DONE)
    {
        clear();
        if (!error)
            error = ERR_UNEXPECTED_EOF;  // unexpected end of file
    }

    return error;
}


// Save to format with depth first ngram traversal
template <class TNGRAMS>
LanguageModel::Error _DynamicModel<TNGRAMS>::
save_depth_first(const char* filename)
{
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

    for (int i=0; i<order; i++)
        fwprintf(f, L"ngram %d=%d\n", i+1, ngrams.get_num_ngrams(i));

    fwprintf(f, L"\n");
    fwprintf(f, L"\\n-grams:\n");

    typename TNGRAMS::iterator it;
    for (it = ngrams.begin(); *it; it++)
    {
        int level = it.get_level();
        fwprintf(f, L"%d %d %ls\n", level,
                                       (*it)->get_count(),
                                       id_to_word((*it)->word_id));
    }

    fwprintf(f, L"\n");
    fwprintf(f, L"\\end\\\n");

    fclose(f);

    return ERR_NONE;
}


