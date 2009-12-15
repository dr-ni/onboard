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
#include <algorithm>

#include "lm_dynamic.h"

using namespace std;

template <class T>
int binsearch(const vector<T>& v, T key)
{
    typename vector<T>::const_iterator it = lower_bound(v.begin(), v.end(), key);
    if (it != v.end() && *it == key)
        return int(it - v.begin());
    return -1;
}

//------------------------------------------------------------------------
// TrieRoot - root node of the ngram trie
//------------------------------------------------------------------------

void TrieRoot::set_order(int order)
{
    this->order = order;
    clear();
}

void TrieRoot::clear()
{
    clear(this, 0);
    num_ngrams = vector<int>(order, 0);
    total_ngrams = vector<int>(order, 0);
    N1pxr = 0;
    N1pxrx = 0;
}

void TrieRoot::clear(BaseNode* node, int level)
{
    if (level < order-1)
    {
        TrieNode* tn = static_cast<TrieNode*>(node);
        std::vector<BaseNode*>::iterator it;
        for (it=tn->children.begin(); it<tn->children.end(); it++)
        {
            clear(*it, level+1);
            if (level < order-2)
                static_cast<TrieNode*>(*it)->~TrieNode();
            else
            if (level < order-1)
                static_cast<BeforeLastNode*>(*it)->~BeforeLastNode();
            MemFree(*it);

        }
        std::vector<BaseNode*>().swap(tn->children);  // really free the memory
    }
    count = 0;
}

// Add increment to node->count and incrementally update kneser-ney counts
int TrieRoot::increment_node_count(BaseNode* node, const WordId* wids, int n, int increment)
{
    // only the first time for each ngram
    if (increment && node->count == 0)
    {
        // get/add node for ngram (wids) excluding predecessor
        // ex: wids = ["We", "saw"] -> wxr = ["saw"] with predecessor "We"
        // Predecessors exist for unigrams or greater, predecessor of unigrams
        // are all unigrams. In that case use the root to store N1pxr.
        vector<WordId> wxr(wids+1, wids+n);
        BaseNode *nd = add_node(wxr);
        if (!nd)
            return -1;
        ((BeforeLastNode*)nd)->N1pxr += 1; // count number of word types wid-n+1
                                           // that precede wid-n+2..wid in the
                                           // training data

        // get/add node for ngram (wids) excluding predecessor and successor
        // ex: wids = ["We", "saw", "whales"] -> wxrx = ["saw"]
        //     with predecessor "We" and successor "whales"
        // Predecessors and successors exist for bigrams or greater. wxrx is
        // an empty vector for bigrams. In that case use the root to store N1pxrx.
        if (n >= 2)
        {
            vector<WordId> wxrx(wids+1, wids+n-1);
            BaseNode* nd = add_node(wxrx);
            if (!nd)
                return -1;
            ((TrieNode*)nd)->N1pxrx += 1;    // count number of word types wid-n+1 that precede wid-n+2..wid in the training data
        }
    }

    total_ngrams[n-1] += increment;
    node->count += increment;
    return node->count;
}

// Look up node or create it if it doesn't exist
BaseNode* TrieRoot::add_node(const WordId* wids, int n)
{
    BaseNode* node = this;
    BaseNode* parent = NULL;
    TrieNode* grand_parent = NULL;
    int parent_index = 0;
    int grand_parent_index = 0;

    for (int i=0; i<n; i++)
    {
        WordId wid = wids[i];
        grand_parent = static_cast<TrieNode*>(parent);
        parent = node;
        grand_parent_index = parent_index;
        node = get_child(parent, i, wid, parent_index);
        if (!node)
        {
            if (i == order-1)
            {
                BeforeLastNode* p = static_cast<BeforeLastNode*>(parent);

                // check the available space for LastNodes
                int size = p->children.size();
                int old_capacity = p->children.capacity();
                if (size >= old_capacity)  // no space for another LastNode?
                {
                    // grow the memory block of the parent node
                    int new_capacity = p->children.capacity(size + 1);
                    int old_bytes = sizeof(BeforeLastNode) +
                               old_capacity*sizeof(LastNode);
                    int new_bytes = sizeof(BeforeLastNode) +
                               new_capacity*sizeof(LastNode);
                    BeforeLastNode* pnew = (BeforeLastNode*) MemAlloc(new_bytes);
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
                int bytes = sizeof(BeforeLastNode) +
                        inplace_vector<LastNode>::capacity(0)*sizeof(LastNode);
                BeforeLastNode* nd = (BeforeLastNode*)MemAlloc(bytes);
                //node = new BeforeLastNode(wid);
                if (!nd)
                    return NULL;
                node = new(nd) BeforeLastNode(wid);
                static_cast<TrieNode*>(parent)->add_child(node);
            }
            else
            {
                TrieNode* nd = (TrieNode*)MemAlloc(sizeof(TrieNode));
                if (!nd)
                    return NULL;
                node = new(nd) TrieNode(wid);
                static_cast<TrieNode*>(parent)->add_child(node);
            }

            num_ngrams[i]++; // keep track of the counts to avoid
                             // traversing the tree for these numbers
            break;
        }
    }
    return node;
}

// reserve an exact number of items to avoid unessarily
// overallocated memory when loading language models
void TrieRoot::reserve_unigrams(int count)
{
    clear();
    children.reserve(count);
}

// Estimate a lower bound for the memory usage of the whole trie.
// This includes overallocations by std::vector, but excludes memory
// used for heap management and possible heap fragmentation.
uint64_t TrieRoot::get_memory_size()
{
    TrieRoot::iterator it = begin();
    uint64_t sum = 0;
    for (; *it; it++)
        sum += get_node_memory_size(*it, it.get_level());
    return sum;
}



//------------------------------------------------------------------------
// LanguageModelDynamic - dynamically updatable language model
//------------------------------------------------------------------------

LanguageModelDynamic::~LanguageModelDynamic()
{
    #ifndef NDEBUG
    uint64_t v = dictionary.get_memory_size();
    uint64_t n = ngrams.get_memory_size();
    printf("memory: dictionary=%ld, ngrams=%ld, total=%ld\n", v, n, v+n);
    #endif

    clear();
}

void LanguageModelDynamic::set_order(int n)
{
    n1s = vector<int>(n, 0);
    n2s = vector<int>(n, 0);
    Ds  = vector<double>(n, 0);
    ngrams.set_order(n);

    LanguageModelNGram::set_order(n);  // calls clear()
}

void LanguageModelDynamic::clear()
{
    LanguageModelNGram::clear();  // clears dictionary

    ngrams.clear();

    // add entries for fixed words
    const wchar_t* words[] = {L"<unk>", L"<s>", L"</s>", L"<num>"};
    for (int i=0; i<ALEN(words); i++)
    {
        count_ngram(words+i, 1, 0);
        assert(dictionary.word_to_id(words[i]) == i);
    }
}

// return a list of word ids to be considered during the prediction
void LanguageModelDynamic::get_candidates(const wchar_t* prefix,
                                          vector<WordId>& wids,
                                          bool filter_control_words)
{
    if (prefix && wcslen(prefix))
    {
        dictionary.prefix_search(prefix, wids);

        // candidate word indices have to be sorted for binsearch in kneser-ney
        sort(wids.begin(), wids.end());
    }
    else
    {
        int size = dictionary.get_num_word_types();
        wids.reserve(size);
        int start = filter_control_words ? NUM_CONTROL_WORDS : 0;
        for (int i=start; i<size; i++)
            wids.push_back(i);
    }
}

// Add increment to the count of the given ngram.
// Unknown words will be added to the dictionary and
// unknown ngrams will cause new trie nodes to be created as needed.
int LanguageModelDynamic::count_ngram(const wchar_t* const* ngram, int n,
                                      int increment, bool allow_new_words)
{
    int i;
    enum {ERR_NONE, ERR_MEMORY_DICT=-1};

    vector<WordId> wids(n);

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
                    return ERR_MEMORY_DICT;
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
int LanguageModelDynamic::count_ngram(const WordId* wids, int n, int increment)
{
    int i;
    enum {ERR_NONE, ERR_MEMORY_NGRAM=-2, ERR_MEMORY_INC=-3}
    error = ERR_NONE;

    // get/add node for ngram
    BaseNode* node = ngrams.add_node(wids, n);
    if (!node)
        return ERR_MEMORY_NGRAM;

    // remove old state
    if (node->count == 1)
        n1s[n-1] -= 1;
    if (node->count == 2)
        n2s[n-1] -= 1;

    if (ngrams.increment_node_count(node, wids, n, increment) < 0)
        return ERR_MEMORY_INC;

    // add new state
    if (node->count == 1)
        n1s[n-1] += 1;
    if (node->count == 2)
        n2s[n-1] += 1;

    // estimate kneser-ney discounting parameters
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

    return error;
}

// Return the number of occurences of the given ngram
int LanguageModelDynamic::get_ngram_count(const wchar_t* const* ngram, int n)
{
    BaseNode* node = get_ngram_node(ngram, n);
    return (node ? node->get_count() : 0);
}

// Calculate a vector of probabilities for the ngrams formed
// from history + word[i], for all i.
// input:  constant history and a vector of candidate words
// output: vector of probabilities, one value per candidate word
void LanguageModelDynamic::get_probs(const vector<WordId>& history,
                            const vector<WordId>& words,
                            vector<double>& probabilities)
{
    // pad/cut history so it's always of length order-1
    int n = min((int)history.size(), order-1);
    vector<WordId> h(order-1, UNKNOWN_WORD_ID);
    copy_backward(history.end()-n, history.end(), h.end());

    #ifndef NDEBUG
    for (int i=0; i<order; i++)
        printf("%d: n1=%8d n2=%8d D=%f\n", i, n1s[i], n2s[i], Ds[i]);
    #endif

    get_probs_kneser_ney_i(h, words, probabilities);
}

// smoothing with kneser_ney interpolation, iterative, vectorized
// input:  constant history and a vector of candidate words
// output: vector of probabilities, one value per candidate word
void LanguageModelDynamic::get_probs_kneser_ney_i(const vector<WordId>& history,
                            const vector<WordId>& words,
                            vector<double>& vp)
{
    // only fixed history size allowed; don't remove unknown words
    // from the history, mark them with UNKNOWN_WORD_ID instead.
    ASSERT((int)history.size() == order-1);

    int i,j;
    int n = history.size() + 1;
    int size = words.size();   // number of candidate words
    vector<int32_t> vc(size);  // vector of counts, reused for order 1..n

    // order 0
    vp.resize(size);
    fill(vp.begin(), vp.end(), 1.0/get_num_word_types()); // uniform distribution

    // order 1..n-1
    for(j=0; j<n-1; j++)
    {
        vector<WordId> h(history.begin()+(n-j-1), history.end()); // tmp history

        // Cast to TrieNode is safe here and below only for history size<=order-2
        // A trigram model will see history sizes of 0 and 1.
        TrieNode* hnode = static_cast<TrieNode*>(ngrams.get_node(h));
        if (hnode)
        {
            // number of permutations around r
            int N1pxrx = hnode->N1pxrx;
            if (N1pxrx)
            {
                double D = Ds[j];
                int N1prx = hnode->get_N1prx(); // number of word types following the history

                // get number of word types seen to precede history h
                if (h.size() == 0) // empty history?
                {
                    // We're at the root and there are many children, all
                    // unigrams to be accurate. So the number of child nodes
                    // is >= the number of candidate words.
                    // Luckily a childs word_id can be directly looked up
                    // in the unigrams because they are always sorted by word_id
                    // as well. -> take that shortcut for root.
                    for(i=0; i<size; i++)
                    {
                        //printf("%d %d %d %d %d\n", size, j, i, words[i], (int)ngrams.children.size());
                        TrieNode* node = static_cast<TrieNode*>(ngrams.children[words[i]]);
                        vc[i] = node->N1pxr;
                    }
                }
                else
                {
                    // We're at some level > 0 and very likely there are much
                    // less child nodes than candidate words. E.g. everything
                    // from bigrams up has in all likelihood only few children.
                    // -> Turn the algorithm around and search the child nodes
                    // in the candidate words.
                    fill(vc.begin(), vc.end(), 0);
                    for(i=0; i<(int)hnode->children.size(); i++)
                    {
                        // children here may be of type TrieNode or BeforeLastNode,
                        // play safe and cast to the latter.
                        BeforeLastNode* child = static_cast<BeforeLastNode*>
                                                           (hnode->children[i]);
                        // word_indices have to be sorted by index
                        int index = binsearch(words, child->word_id);
                        if (index != -1)
                            vc[index] = child->N1pxr;
                    }

                    #ifndef NDEBUG
                    // brute force search for testing
                    // slower but should always work
                    // overrides the above
                    vector<WordId> ngram = h;
                    ngram.push_back(0);
                    for(i=0; i<(int)vc.size(); i++)
                    {
                        ngram.back() = words[i];
                        BeforeLastNode* node = static_cast<BeforeLastNode*>
                                                (ngrams.get_node(ngram));
                        vc[i] = node ? node->N1pxr : 0;

                        if(node)
                        {
                            printf("vc: ngram=");
                            print_ngram(ngram);
                            printf("vc: wid=%d N1pxr=%d\n", node->word_id, node->N1pxr);
                        }
                    }
                    #endif
                }
                #ifndef NDEBUG
                int s=0;
                for(i=0; i<(int)vc.size(); i++)
                    s += vc[i];
                print_ngram(h);
                printf("order=%d N1prx=%d N1pxrx=%d %d %d\n", j+1, N1prx, N1pxrx, s, (int)h.size());
                #endif

                double a;
                double g = D / float(N1pxrx) * N1prx; // normalization factor
                                                      // 1 - gamma
                for(i=0; i<size; i++)
                {
                    a = vc[i] - D;
                    if (a < 0)
                        a = 0;
                    vp[i] = a / N1pxrx + g * vp[i];
                }
            }
        }
    }

    // order n
    // The history ought to be always at the second to last node level
    BeforeLastNode* hnode = static_cast<BeforeLastNode*>
                                       (ngrams.get_node(history));
    if (hnode)
    {
        int cs;
        if (n == 1)
            // currently never reached; was meant for order 1 language models
            cs = ngrams.get_num_ngrams(0);
        else
            cs = ngrams.get_ngram_count(history); // sum_w(c(history+w)) = c(history)
        if (cs)
        {
            double D = Ds[n-1];
            int N1prx = hnode->get_N1prx();   // number of word types following the history

            // get ngram counts
            fill(vc.begin(), vc.end(), 0);
            for(i=0; i<(int)hnode->children.size(); i++)
            {
                BaseNode* child = &hnode->children[i];
                int index = binsearch(words, child->word_id); // word_indices have to be sorted by index
                if (index >= 0)
                    vc[index] = child->get_count();
            }
            #ifndef NDEBUG
            vector<WordId> ngram = history;
            ngram.push_back(0);
            for(i=0; i<(int)vc.size(); i++)
            {
                ngram[n-1] = words[i];
                BaseNode* node = ngrams.get_node(ngram);
                vc[i] = node ? node->count : 0;
            }
            int s=0;
            for(i=0; i<(int)vc.size(); i++)
                s += vc[i];
            printf("order=%d N1prx=%d cs=%d D=%f n1=%d n2=%d %d\n", n, N1prx, cs, D, n1s[n-1], n2s[n-1], s);
            #endif

            double a;
            double g = D / float(cs) * N1prx; // normalization factor
                                              // 1 - gamma
            for(i=0; i<size; i++)
            {
                a = vc[i] - D;
                if (a < 0)
                    a = 0;
                vp[i] = a / cs + g * vp[i];
            }
        }
    }
}

// Load from ARPA like format, expects counts instead of log probabilities
// and no back-off values. N-grams don't have to be sorted alphabetically.
int LanguageModelDynamic::load_arpac(const char* filename)
{
    int i;
    int new_order = 0;
    int current_level = 0;
    vector<int> counts;

    enum {ERR_NONE, ERR_FILE, ERR_MEMORY, ERR_NUMTOKENS,
          ERR_ORDER, ERR_COUNT, ERR_END}
    error = ERR_NONE;

    enum {BEGIN, COUNTS, NGRAMS_HEAD, NGRAMS, DONE}
    state = BEGIN;

    // clear language model
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
            // check for n-grams first for speed
            if (state == NGRAMS)
            {
                if (tokens[0][0] == L'\\')
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
                    int count = wcstol(tokens[0], NULL, 10);
                    if (ntoks < current_level+1)
                    {
                        error = ERR_NUMTOKENS; // too few tokens for current ngram level
                        break;
                    }
                    int err = count_ngram(tokens+1, current_level, count);
                    if (err)
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
                        new_order = max(new_order, level);
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
            error = ERR_END;  // unexpected end of file
    }

    return error;
}

// Save to ARPA like format, stores counts instead of log probabilities
// and no back-off values.
int LanguageModelDynamic::save_arpac(const char* filename)
{
    int i;

    FILE* f = fopen(filename, "w,ccs=UTF-8");
    if (!f)
    {
        #ifndef NDEBUG
        printf( "Error opening %s\n", filename);
        #endif
        return -1;
    }

    fwprintf(f, L"\n");
    fwprintf(f, L"\\data\\\n");

    for (i=0; i<order; i++)
        fwprintf(f, L"ngram %d=%d\n", i+1, ngrams.get_num_ngrams(i));

    for (i=0; i<order; i++)
    {
        fwprintf(f, L"\n");
        fwprintf(f, L"\\%d-grams:\n", i+1);

        TrieRoot::iterator it = ngrams.begin();
        vector<WordId> wids;
        for (it = ngrams.begin(); *it; it++)
        {
            if (it.get_level() == i+1)
            {
                it.get_ngram(wids);
                fwprintf(f, L"%d", (*it)->get_count());
                for(int j=0; j<=i; j++)
                    fwprintf(f, L" %ls", id_to_word(wids[j]));
                fwprintf(f, L"\n");
            }
        }
    }

    fwprintf(f, L"\n");
    fwprintf(f, L"\\end\\\n");

    fclose(f);

    return 0;
}

// load from format with depth first ngram traversal
// not much faster than load_arpa and more unusual file format -> disabled
int LanguageModelDynamic::load_depth_first(const char* filename)
{
    int i;
    int new_order = 0;
    vector<int> counts;
    vector<WordId> wids;

    enum {ERR_NONE, ERR_FILE, ERR_MEMORY, ERR_NUMTOKENS,
          ERR_ORDER, ERR_COUNT, ERR_END}
    error = ERR_NONE;

    enum {BEGIN, COUNTS, NGRAMS_HEAD, NGRAMS, END, DONE}
    state = BEGIN;

    // clear language model
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
                        error = ERR_COUNT; // count doesn't match number of unique ngrams
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

                    int err = count_ngram(&wids[0], level, count);
                    if (err)
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
                        new_order = max(new_order, level);
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
                        wids = vector<WordId>(new_order, 0);
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
            error = ERR_END;  // unexpected end of file
    }

    return error;
}


// Save to format with depth first ngram traversal
int LanguageModelDynamic::save_depth_first(const char* filename)
{
    FILE* f = fopen(filename, "w,ccs=UTF-8");
    if (!f)
    {
        #ifndef NDEBUG
        printf( "Error opening %s\n", filename);
        #endif
        return -1;
    }

    fwprintf(f, L"\n");
    fwprintf(f, L"\\data\\\n");

    for (int i=0; i<order; i++)
        fwprintf(f, L"ngram %d=%d\n", i+1, ngrams.get_num_ngrams(i));

    fwprintf(f, L"\n");
    fwprintf(f, L"\\n-grams:\n");

    TrieRoot::iterator it = ngrams.begin();
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

    return 0;
}


