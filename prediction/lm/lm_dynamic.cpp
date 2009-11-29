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
    num_ngrams = vector<int>(order, 0);
    this->order = order;
}

void TrieRoot::clear()
{
    clear(this, 0);
    num_ngrams = vector<int>(order, 0);
    total_ngrams = vector<int>(order, 0);
    N1pxr = 0;
    N1pxrx = 0;
}

int TrieRoot::increment_node_count(BaseNode* node, const vector<int>& wids, int increment)
{
    int n = wids.size();

    // only the first time for each ngram
    if (increment && node->count == 0)
    {
        // get/add node for ngram excluding predecessor
        // Predecessors exist for unigrams or greater,
        // Use root for empty remainder, i.e. predecessor of nothing are all unigrams
        vector<int32_t> wxr(wids.begin()+1, wids.end());
        BaseNode *nd = add_node(wxr);
        if (!nd)
            return -1;
        ((BeforeLastNode*)nd)->N1pxr += 1;    // count number of word types wid-n+1 that precede wid-n+2..wid in the training data

        // get/add node for ngram excluding predecessor and successor
        // Predecessors and successors exist only for bigrams or greater.
        // Use root for empty remainder, i.e. nothing is surrounded by all bigrams.
        if (n >= 2)
        {
            vector<int32_t> wxrx(wids.begin()+1, wids.end()-1);
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

// looks up node or creates it if it doesn't exist
BaseNode* TrieRoot::add_node(const vector<int>& wids)
{
    BaseNode* node = this;
    BaseNode* parent = NULL;
    TrieNode* grand_parent = NULL;
    int parent_index = 0;
    int grand_parent_index = 0;

    for (int i=0; i<(int)wids.size(); i++)
    {
        int wid = wids[i];
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
                if (size >= old_capacity)
                {
                    // grow the memory block of the parent node
                    int new_capacity = p->children.capacity(size + 1);
                    int old_bytes = sizeof(BeforeLastNode) +
                               old_capacity*sizeof(LastNode);
                    int new_bytes = sizeof(BeforeLastNode) +
                               new_capacity*sizeof(LastNode);
                    BeforeLastNode* pnew = (BeforeLastNode*)
                                           (new uint8_t[new_bytes]);
                    if (!pnew)
                        return NULL;

                    // copy the data over, no need for constructor calls
                    memcpy(pnew, p, old_bytes);

                    // replace grand_parent pointer
                    ASSERT(p == grand_parent->children[grand_parent_index]);
                    grand_parent->children[grand_parent_index] = pnew;
                    delete p;
                    p = pnew;
                }

                // add the new child node
                node = p->add_child(wid);
            }
            else
            if (i == order-2)
            {
                node = new BeforeLastNode(wid);
                if (!node)
                    return NULL;
                static_cast<TrieNode*>(parent)->add_child(node);
            }
            else
            {
                node = new TrieNode(wid);
                if (!node)
                    return NULL;
                static_cast<TrieNode*>(parent)->add_child(node);
            }

            num_ngrams[i]++; // keep track of the counts to avoid
                             // traversing the tree for these numbers
            break;
        }
    }
    return node;
}

// reserve exact number of items to avoid unessarily
// overallocated memory when loading language models
void TrieRoot::reserve_unigrams(int count)
{
    clear();
    children.reserve(count);
}

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
    uint64_t v = dictionary.get_memory_size();
    uint64_t n = ngrams.get_memory_size();
    printf("memory: dictionary=%ld, ngrams=%ld, total=%ld\n", v, n, v+n);
    clear();
}

void LanguageModelDynamic::set_order(int n)
{
    n1s = vector<int>(n, 0);
    n2s = vector<int>(n, 0);
    Ds = vector<double>(n, 0);
    ngrams.set_order(n);

    LanguageModelNGram::set_order(n);
}

void LanguageModelDynamic::clear()
{
    LanguageModelNGram::clear();

    ngrams.clear();

    // add entry for unknown words
    const wchar_t* ngram[] = {L"<unk>"};
    count_ngram(ngram, sizeof(ngram)/sizeof(*ngram), 0);
    ASSERT(dictionary.word_to_id(L"<unk>") == UNKNOWN_WORD_ID);
}



void LanguageModelDynamic::get_candidates(const wchar_t* prefix, vector<int32_t>& wids)
{
    if (wcslen(prefix))
    {
        dictionary.search_prefix(prefix, wids);

        // candidate word indices have to be sorted for binsearch in kneser-ney
        sort(wids.begin(), wids.end());
    }
    else
    {
        int size = dictionary.get_num_word_types();
        wids.resize(size);
        for (int i=0; i<size; i++)
            wids[i] = i;
    }
}

int LanguageModelDynamic::count_ngram(const wchar_t* const words[], int n, int increment)
{
    int i;
    int error = 0;

    vector<int> wids(n);

    // get/add word
    for (i = 0; i < n; i++)
    {
        const wchar_t* word = words[i];

        int wid = dictionary.word_to_id(word);
        if (wid == -1)
        {
            wid = dictionary.add_word(word);
            if (wid < 0)
                return -1;
        }
        wids[i] = wid;
    }

    // get/add node for ngram
    BaseNode* node = ngrams.add_node(wids);
    if (!node)
        return -2;

    // remove old state
    if (node->count == 1)
        n1s[n-1] -= 1;
    if (node->count == 2)
        n2s[n-1] -= 1;

    if (ngrams.increment_node_count(node, wids, increment) < 0)
        return -3;

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

int LanguageModelDynamic::get_ngram_count(const wchar_t* words[], int n)
{
    BaseNode* node = get_ngram_node(words, n);
    return (node ? node->get_count() : 0);
}

void LanguageModelDynamic::get_probs(const vector<int32_t>& history,
                            const vector<int32_t>& words,
                            vector<double>& probabilities)
{
    // pad/cut history so it's always of length order-1
    int n = min((int)history.size(), order-1);
    vector<int32_t> h(order-1, UNKNOWN_WORD_ID);
    copy_backward(history.end()-n, history.end(), h.end());

    #ifdef _DEBUG
    for (int i=0; i<order; i++)
        printf("%d: n1=%8d n2=%8d D=%f\n", i, n1s[i], n2s[i], Ds[i]);
    #endif

    get_probs_kneser_ney_i(h, words, probabilities);
}

// smoothing with kneser_ney interpolation, iterative, vectorized
// input:  constant history and a vector of candidate words
// output: vector of probabilities, one value per candidate word
void LanguageModelDynamic::get_probs_kneser_ney_i(const vector<int32_t>& history,
                            const vector<int32_t>& words,
                            vector<double>& vp)
{
    // only fixed history size allowed, mark unknown words with UNKNOWN_WORD_ID
    ASSERT(history.size() == order-1);

    int i,j;
    int n = history.size() + 1;
    int size = words.size();   // number of candidate words
    vector<int32_t> vc(size);  // counts, reused for order 1..n

    // order 0
    vp.resize(size);
    fill(vp.begin(), vp.end(), 1.0/get_num_word_types()); // uniform distribution

    // order 1..n-1
    for(j=0; j<n-1; j++)
    {
        vector<int32_t> h(history.begin()+(n-j-1), history.end());

        // Cast to TrieNode is safe here and below only for history size<=order-2
        // A trigram model will see history size of 0 and 1
        TrieNode* hnode = static_cast<TrieNode*>(ngrams.get_node(h));
        if (hnode)
        {
            // number of permutations around r
            int N1pxrx = hnode->N1pxrx;
            if (N1pxrx)
            {
                double D = Ds[j];
                int N1prx = hnode->get_N1prx(); // number of word types following the history

                // number of word types seen to precede ngram
                if (h.size() == 0)
                {
                    // number of children >= number candidate words
                    // -> shortcut for root, all unigrams exist there
                    for(i=0; i<size; i++)
                    {
                        //printf("%d %d %d %d %d\n", size, j, i, words[i], (int)ngrams.children.size());
                        TrieNode* node = static_cast<TrieNode*>(ngrams.children[words[i]]);
                        vc[i] = node->N1pxr;
                    }
                }
                else
                {
                    // number of children << number of searched words
                    // everything from bigrams in all likelihood has only few children
                    fill(vc.begin(), vc.end(), 0);
                    for(i=0; i<(int)hnode->children.size(); i++)
                    {
                        // children here may be TrieNode or BeforeLastNode,
                        // play safe and cast to the latter.
                        BeforeLastNode* child = static_cast<BeforeLastNode*>
                                                           (hnode->children[i]);
                        // word_indices have to be sorted by index
                        int index = binsearch(words, (int32_t)child->word_id);
                        if (index != -1)
                            vc[index] = child->N1pxr;
                    }

                    #ifdef _DEBUG
                    vector<int> ngram = h;
                    ngram.push_back(0);
                    //BREAK;
                    for(i=0; i<(int)vc.size(); i++)
                    {
                        ngram.back() = words[i];
                        BeforeLastNode* node = static_cast<BeforeLastNode*>
                                                (ngrams.get_node(ngram));
                        vc[i] = node ? node->N1pxr : 0;

                        if(node)
                        {
                            //BREAK;
                            printf("vc: ngram=");
                            print_ngram(ngram);
                            printf("vc: wid=%d N1pxr=%d\n", node->word_id, node->N1pxr);
                        }
                    }
                    #endif
                }
                #ifdef _DEBUG
                int s=0;
                for(i=0; i<(int)vc.size(); i++)
                    s += vc[i];
                print_ngram(h);
                printf("order=%d N1prx=%d N1pxrx=%d %d %d\n", j+1, N1prx, N1pxrx, s, (int)h.size());
                #endif

                double a;
                double g = D / float(N1pxrx) * N1prx;     // 1 - gamma
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
    // This ought to be always the second to last node level
    BeforeLastNode* hnode = static_cast<BeforeLastNode*>
                                       (ngrams.get_node(history));
    if (hnode)
    {
        int cs;
        if (n == 1)
            cs = ngrams.get_num_ngrams(0);
        else
            cs = ngrams.get_ngram_count(history);   // sum_w(c(history+w)) = c(history)
        if (cs)
        {
            double D = Ds[n-1];
            int N1prx = hnode->get_N1prx();   // number of word types following the history

            // get ngram counts
            fill(vc.begin(), vc.end(), 0);
            for(i=0; i<(int)hnode->children.size(); i++)
            {
                BaseNode* child = &hnode->children[i];
                int index = binsearch(words, (int32_t)child->word_id); // word_indices have to be sorted by index
                if (index >= 0)
                    vc[index] = child->get_count();
            }
            #ifdef _DEBUG
            vector<int> ngram = history;
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
            double g = D / float(cs) * N1prx;     // 1 - gamma
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

int LanguageModelDynamic::load(char* filename)
{
    int i;
    int error = 0;
    int new_order = 0;
    int current_level = 0;
    vector<int> counts;

    enum {BEGIN, COUNTS, NGRAMS_HEAD, NGRAMS, DONE};
    int state = BEGIN;

    // clear language model
    clear();


    FILE* f = fopen(filename, "r,ccs=UTF-8");
    if (!f)
    {
        #ifdef _DEBUG
        printf( "Error opening %s\n", filename);
        #endif
        return -1;
    }

    //BREAK;
    while(1)
    {
        wchar_t buf[2048];
        if (fgetws(buf, ALEN(buf), f) == NULL)
            break;

        wchar_t *tstate;
        wchar_t* tokens[32] = {wcstok(buf, L" \n", &tstate)};
        for (i=0; tokens[i] && i < ALEN(tokens)-1; i++)
            tokens[i+1] = wcstok(NULL, L" \n", &tstate);
        int ntoks = i;

        if (ntoks)
        {
            if (state == NGRAMS)
            {
                if (tokens[0][0] == L'\\')
                {
                    if (ngrams.get_num_ngrams(current_level-1) !=
                        counts[current_level-1])
                    {
                        error = -4; // count doesn't match number of unique ngrams
                        break;
                    }
                    state = NGRAMS_HEAD;
                }
                else
                {
                    int count = wcstol(tokens[0], NULL, 10);
                    if (ntoks < current_level+1)
                    {
                        // too few tokens for current ngram level
                        error = -3;
                    }
                    count_ngram(tokens+1, current_level, count);

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
                        error = -2;
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
    }

    return error;
}

int LanguageModelDynamic::save(char* filename)
{
    int i;

    FILE* f = fopen(filename, "w,ccs=UTF-8");
    if (!f)
    {
        #ifdef _DEBUG
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
        vector<int> ngram;
        for (it = ngrams.begin(); *it; it++)
        {
            if (it.get_level() == i+1)
            {
                it.get_ngram(ngram);
                fwprintf(f, L"%d", (*it)->get_count());
                for(int j=0; j<=i; j++)
                    fwprintf(f, L" %ls", id_to_word(ngram[j]));
                fwprintf(f, L"\n");
            }
        }
    }

    fwprintf(f, L"\n");
    fwprintf(f, L"\\end\\\n");

    fclose(f);

    return 0;
}


